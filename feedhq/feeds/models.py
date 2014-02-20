# -*- coding: utf-8 -*-
import bleach
import datetime
import feedparser
import hashlib
import json
import logging
import lxml.html
import magic
import oauth2 as oauth
import urllib
import urlparse
import random
import requests
import socket
import struct
import time

from django.db import models
from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.urlresolvers import reverse, reverse_lazy
from django.template.defaultfilters import slugify
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.html import format_html
from django.utils.text import unescape_entities
from django.utils.translation import ugettext_lazy as _, string_concat
from django_push.subscriber.signals import updated
from httplib import IncompleteRead
from lxml.etree import ParserError
from rache import schedule_job, delete_job
from requests.exceptions import ConnectionError
from requests.packages.urllib3.exceptions import (LocationParseError,
                                                  DecodeError)

import pytz

from .fields import URLField
from .tasks import (update_feed, update_favicon, store_entries,
                    ensure_subscribed)
from .utils import (FAVICON_FETCHER, USER_AGENT, is_feed, epoch_to_utc,
                    get_job, JobNotFound)
from ..storage import OverwritingStorage
from ..tasks import enqueue
from ..utils import get_redis_connection

logger = logging.getLogger(__name__)

feedparser.PARSE_MICROFORMATS = False
feedparser.SANITIZE_HTML = False

COLORS = (
    ('red', _('Red')),
    ('dark-red', _('Dark Red')),
    ('pale-green', _('Pale Green')),
    ('green', _('Green')),
    ('army-green', _('Army Green')),
    ('pale-blue', _('Pale Blue')),
    ('blue', _('Blue')),
    ('dark-blue', _('Dark Blue')),
    ('orange', _('Orange')),
    ('dark-orange', _('Dark Orange')),
    ('black', _('Black')),
    ('gray', _('Gray')),
)


def random_color():
    return random.choice(COLORS)[0]


def timedelta_to_seconds(delta):
    return delta.days * 3600 * 24 + delta.seconds


def enqueue_favicon(url, force_update=False):
    enqueue(update_favicon, args=[url], kwargs={'force_update': force_update},
            queue='favicons')


class CategoryManager(models.Manager):
    def with_unread_counts(self):
        return self.values('id', 'name', 'slug', 'color').annotate(
            unread_count=models.Sum('feeds__unread_count'))


class Category(models.Model):
    """Used to sort our feeds"""
    name = models.CharField(_('Name'), max_length=1023, db_index=True)
    slug = models.SlugField(_('Slug'), db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('User'),
                             related_name='categories')
    # Some day there will be drag'n'drop ordering
    order = models.PositiveIntegerField(blank=True, null=True)

    # Categories have nice cute colors
    color = models.CharField(_('Color'), max_length=50, choices=COLORS,
                             default=random_color)

    objects = CategoryManager()

    def __unicode__(self):
        return u'%s' % self.name

    class Meta:
        ordering = ('order', 'name', 'id')
        verbose_name_plural = 'categories'
        unique_together = (
            ('user', 'slug'),
            ('user', 'name'),
        )

    def get_absolute_url(self):
        return reverse('feeds:category', args=[self.slug])

    def save(self, *args, **kwargs):
        update_slug = kwargs.pop('update_slug', False)
        if not self.slug or update_slug:
            slug = slugify(self.name)
            if not slug:
                slug = 'unknown'
            valid = False
            candidate = slug
            num = 1
            while not valid:
                if candidate in ('add', 'import'):  # gonna conflict
                    candidate = '{0}-{1}'.format(slug, num)
                categories = self.user.categories.filter(slug=candidate)
                if self.pk is not None:
                    categories = categories.exclude(pk=self.pk)
                if categories.exists():
                    candidate = '{0}-{1}'.format(slug, num)
                    num += 1
                else:
                    valid = True
            self.slug = candidate
        return super(Category, self).save(*args, **kwargs)


class UniqueFeedManager(models.Manager):
    def update_feed(self, url, etag=None, last_modified=None, subscribers=1,
                    backoff_factor=1, previous_error=None, link=None,
                    title=None, hub=None):

        # Check if this domain has rate-limiting rules
        domain = urlparse.urlparse(url).netloc
        ratelimit_key = 'ratelimit:{0}'.format(domain)
        retry_at = cache.get(ratelimit_key)
        if retry_at:
            retry_in = (epoch_to_utc(retry_at) - timezone.now()).seconds
            schedule_job(url, schedule_in=retry_in,
                         connection=get_redis_connection())
            return

        if subscribers == 1:
            subscribers_text = '1 subscriber'
        else:
            subscribers_text = '{0} subscribers'.format(subscribers)

        headers = {
            'User-Agent': USER_AGENT % subscribers_text,
            'Accept': feedparser.ACCEPT_HEADER,
        }

        if last_modified:
            headers['If-Modified-Since'] = force_bytes(last_modified)
        if etag:
            headers['If-None-Match'] = force_bytes(etag)

        if settings.TESTS:
            # Make sure requests.get is properly mocked during tests
            if str(type(requests.get)) != "<class 'mock.MagicMock'>":
                raise ValueError("Not Mocked")

        start = datetime.datetime.now()
        error = None
        try:
            response = requests.get(
                url, headers=headers,
                timeout=UniqueFeed.request_timeout(backoff_factor))
        except (requests.RequestException, socket.timeout, socket.error,
                IncompleteRead, DecodeError) as e:
            logger.debug("Error fetching %s, %s" % (url, str(e)))
            if isinstance(e, IncompleteRead):
                error = UniqueFeed.CONNECTION_ERROR
            elif isinstance(e, DecodeError):
                error = UniqueFeed.DECODE_ERROR
            else:
                error = UniqueFeed.TIMEOUT
            self.backoff_feed(url, error, backoff_factor)
            return
        except LocationParseError:
            logger.debug(u"Failed to parse URL for {0}".format(url))
            self.mute_feed(url, UniqueFeed.PARSE_ERROR)
            return

        elapsed = (datetime.datetime.now() - start).seconds

        ctype = response.headers.get('Content-Type', None)
        if (response.history and
            url != response.url and ctype is not None and (
                ctype.startswith('application') or
                ctype.startswith('text/xml') or
                ctype.startswith('text/rss'))):
            redirection = None
            for index, redirect in enumerate(response.history):
                if redirect.status_code != 301:
                    break
                # Actual redirection is next request's url
                try:
                    redirection = response.history[index + 1].url
                except IndexError:  # next request is final request
                    redirection = response.url

            if redirection is not None and redirection != url:
                self.handle_redirection(url, redirection)

        update = {'last_update': int(time.time())}

        if response.status_code == 410:
            logger.debug(u"Feed gone, {0}".format(url))
            self.mute_feed(url, UniqueFeed.GONE)
            return

        elif response.status_code in [400, 401, 403, 404, 500, 502, 503]:
            self.backoff_feed(url, str(response.status_code), backoff_factor)
            return

        elif response.status_code not in [200, 204, 304]:
            logger.debug(u"{0} returned {1}".format(url, response.status_code))

            if response.status_code == 429:
                # Too Many Requests
                # Prevent next jobs from fetching the URL before retry-after
                retry_in = int(response.headers.get('Retry-After', 60))
                retry_at = timezone.now() + datetime.timedelta(
                    seconds=retry_in)
                cache.set(ratelimit_key,
                          int(retry_at.strftime('%s')),
                          retry_in)
                schedule_job(url, schedule_in=retry_in)
                return

        else:
            # Avoid going back to 1 directly if it isn't safe given the
            # actual response time.
            if previous_error and error is None:
                update['error'] = None
            backoff_factor = min(backoff_factor, self.safe_backoff(elapsed))
            update['backoff_factor'] = backoff_factor

        if response.status_code == 304:
            schedule_job(url,
                         schedule_in=UniqueFeed.delay(backoff_factor, hub),
                         connection=get_redis_connection(), **update)
            return

        if 'etag' in response.headers:
            update['etag'] = response.headers['etag']
        else:
            update['etag'] = None

        if 'last-modified' in response.headers:
            update['modified'] = response.headers['last-modified']
        else:
            update['modified'] = None

        try:
            if not response.content:
                content = ' '  # chardet won't detect encoding on empty strings
            else:
                content = response.content
        except socket.timeout:
            logger.debug(u'{0} timed out'.format(url))
            self.backoff_feed(url, UniqueFeed.TIMEOUT, backoff_factor)
            return

        parsed = feedparser.parse(content)

        if not is_feed(parsed):
            self.backoff_feed(url, UniqueFeed.NOT_A_FEED,
                              UniqueFeed.MAX_BACKOFF)
            return

        if 'link' in parsed.feed and parsed.feed.link != link:
            update['link'] = parsed.feed.link

        if 'title' in parsed.feed and parsed.feed.title != title:
            update['title'] = parsed.feed.title

        if 'links' in parsed.feed:
            for link in parsed.feed.links:
                if link.rel == 'hub':
                    update['hub'] = link.href
        if 'hub' not in update:
            update['hub'] = None
        else:
            subs_key = u'pshb:{0}'.format(url)
            enqueued = cache.get(subs_key)
            if not enqueued:
                cache.set(subs_key, True, 3600 * 24)
                enqueue(ensure_subscribed, args=[url, update['hub']],
                        queue='store')

        schedule_job(url,
                     schedule_in=UniqueFeed.delay(
                         update.get('backoff_factor', backoff_factor),
                         update['hub']),
                     connection=get_redis_connection(), **update)

        entries = filter(
            None,
            [self.entry_data(entry, parsed) for entry in parsed.entries]
        )
        if len(entries):
            enqueue(store_entries, args=[url, entries], queue='store')

    @classmethod
    def entry_data(cls, entry, parsed):
        if not 'link' in entry:
            return
        title = entry.title if 'title' in entry else u''
        if len(title) > 255:  # FIXME this is gross
            title = title[:254] + u'…'
        entry_date, date_generated = cls.entry_date(entry)
        data = {
            'title': title,
            'link': entry.link,
            'date': entry_date,
            'author': entry.get('author', parsed.get('author', ''))[:1023],
            'guid': entry.get('id', entry.link),
            'date_generated': date_generated,
        }
        if not data['guid']:
            data['guid'] = entry.link
        if not data['guid']:
            data['guid'] = entry.title
        if not data['guid']:
            return
        if 'description' in entry:
            data['subtitle'] = entry.description
        if 'summary' in entry:
            data['subtitle'] = entry.summary
        if 'content' in entry:
            data['subtitle'] = ''

            # If there are several types, promote html. text items
            # can be duplicates.
            selected_type = None
            types = set([c['type'] for c in entry.content])
            if len(types) > 1 and 'text/html' in types:
                selected_type = 'text/html'
            for content in entry.content:
                if selected_type is None or content['type'] == selected_type:
                    data['subtitle'] += content.value
        if 'subtitle' in data:
            data['subtitle'] = u'<div>{0}</div>'.format(data['subtitle'])
        return data

    @classmethod
    def entry_date(cls, entry):
        date_generated = False
        if 'published_parsed' in entry and entry.published_parsed is not None:
            field = entry.published_parsed
        elif 'updated_parsed' in entry and entry.updated_parsed is not None:
            field = entry.updated_parsed
        else:
            field = None

        if field is None:
            entry_date = timezone.now()
            date_generated = True
        else:
            entry_date = timezone.make_aware(
                datetime.datetime(*field[:6]),
                pytz.utc,
            )
            # Sometimes entries are published in the future. If they're
            # published, it's probably safe to adjust the date.
            if entry_date > timezone.now():
                entry_date = timezone.now()
        return entry_date, date_generated

    def handle_redirection(self, old_url, new_url):
        logger.debug(u"{0} moved to {1}".format(old_url, new_url))
        Feed.objects.filter(url=old_url).update(url=new_url)
        unique, created = self.get_or_create(url=new_url)
        if created:
            unique.schedule()
            if not settings.TESTS:
                enqueue_favicon(new_url)
        self.filter(url=old_url).delete()
        delete_job(old_url, connection=get_redis_connection())

    def mute_feed(self, url, reason):
        delete_job(url, connection=get_redis_connection())
        self.filter(url=url).update(muted=True, error=reason)

    def backoff_feed(self, url, error, backoff_factor):
        if backoff_factor == UniqueFeed.MAX_BACKOFF - 1:
            logger.debug(u"{0} reached max backoff period ({1})".format(
                url, error,
            ))
        backoff_factor = min(UniqueFeed.MAX_BACKOFF, backoff_factor + 1)
        schedule_job(url, schedule_in=UniqueFeed.delay(backoff_factor),
                     error=error, backoff_factor=backoff_factor,
                     connection=get_redis_connection())

    def safe_backoff(self, response_time):
        """
        Returns the backoff factor that should be used to keep the feed
        working given the last response time. Keep a margin. Backoff time
        shouldn't increase, this is only used to avoid returning back to 10s
        if the response took more than that.
        """
        return int((response_time * 1.2) / 10) + 1


class JobDataMixin(object):
    @property
    def job_details(self):
        if hasattr(self, 'muted') and self.muted:
            return {}
        if not hasattr(self, '_job_details'):
            self._job_details = get_job(self.url)
        return self._job_details

    @property
    def safe_job_details(self):
        """
        For use in templates -- when raising JobNotFound is not
        acceptable.
        """
        try:
            return self.job_details
        except JobNotFound:
            return

    @property
    def scheduler_data(self):
        return json.dumps(self.job_details, indent=4, sort_keys=True)

    @property
    def next_update(self):
        return epoch_to_utc(self.job_details['schedule_at'])

    @property
    def last_update(self):
        try:
            update = self.job_details.get('last_update')
        except JobNotFound:
            return
        if update is not None:
            return epoch_to_utc(update)

    @property
    def link(self):
        try:
            return self.job_details.get('link', self.url)
        except JobNotFound:
            return self.url


class UniqueFeed(JobDataMixin, models.Model):
    GONE = 'gone'
    TIMEOUT = 'timeout'
    PARSE_ERROR = 'parseerror'
    CONNECTION_ERROR = 'connerror'
    DECODE_ERROR = 'decodeerror'
    NOT_A_FEED = 'notafeed'
    HTTP_400 = '400'
    HTTP_401 = '401'
    HTTP_403 = '403'
    HTTP_404 = '404'
    HTTP_500 = '500'
    HTTP_502 = '502'
    HTTP_503 = '503'
    MUTE_CHOICES = (
        (GONE, 'Feed gone (410)'),
        (TIMEOUT, 'Feed timed out'),
        (PARSE_ERROR, 'Location parse error'),
        (CONNECTION_ERROR, 'Connection error'),
        (DECODE_ERROR, 'Decoding error'),
        (NOT_A_FEED, 'Not a valid RSS/Atom feed'),
        (HTTP_400, 'HTTP 400'),
        (HTTP_401, 'HTTP 401'),
        (HTTP_403, 'HTTP 403'),
        (HTTP_404, 'HTTP 404'),
        (HTTP_500, 'HTTP 500'),
        (HTTP_502, 'HTTP 502'),
        (HTTP_503, 'HTTP 503'),
    )
    MUTE_DICT = dict(MUTE_CHOICES)

    url = URLField(_('URL'), unique=True)
    muted = models.BooleanField(_('Muted'), default=False, db_index=True)
    error = models.CharField(_('Error'), max_length=50, null=True, blank=True,
                             choices=MUTE_CHOICES, db_column='muted_reason')

    objects = UniqueFeedManager()

    MAX_BACKOFF = 10  # Approx. 24 hours
    UPDATE_PERIOD = 60  # in minutes
    BACKOFF_EXPONENT = 1.5
    TIMEOUT_BASE = 20
    JOB_ATTRS = ['modified', 'etag', 'backoff_factor', 'error', 'link',
                 'title', 'hub', 'subscribers', 'last_update']

    def __unicode__(self):
        return u'%s' % self.url

    def truncated_url(self):
        if len(self.url) > 50:
            return self.url[:49] + u'…'
        return self.url
    truncated_url.short_description = _('URL')
    truncated_url.admin_order_field = 'url'

    @classmethod
    def request_timeout(cls, backoff_factor):
        return 10 * backoff_factor

    @classmethod
    def delay(cls, backoff_factor, hub=None):
        if hub is not None:
            backoff_factor = max(backoff_factor, 3)
        return datetime.timedelta(
            seconds=60 * cls.UPDATE_PERIOD *
            backoff_factor ** cls.BACKOFF_EXPONENT)

    @property
    def schedule_in(self):
        return (
            self.last_update + self.delay(self.job_details['backoff_factor'],
                                          self.job_details.get('hub'))
        ) - timezone.now()

    def schedule(self, schedule_in=None, **job):
        if hasattr(self, '_job_details'):
            del self._job_details
        connection = get_redis_connection()
        kwargs = {
            'subscribers': 1,
            'backoff_factor': 1,
            'last_update': int(time.time()),
        }
        kwargs.update(job)
        if schedule_in is None:
            try:
                for attr in self.JOB_ATTRS:
                    if attr in self.job_details:
                        kwargs[attr] = self.job_details[attr]
                schedule_in = self.schedule_in
            except JobNotFound:
                schedule_in = self.delay(kwargs['backoff_factor'])
        schedule_job(self.url, schedule_in=schedule_in,
                     connection=connection, **kwargs)


class Feed(JobDataMixin, models.Model):
    """A URL and some extra stuff"""
    name = models.CharField(_('Name'), max_length=1023)
    url = URLField(_('URL'))
    category = models.ForeignKey(
        Category, verbose_name=_('Category'), related_name='feeds',
        help_text=string_concat('<a href="',
                                reverse_lazy('feeds:add_category'), '">',
                                _('Add a category'), '</a>'),
        null=True, blank=True,
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('User'),
                             related_name='feeds')
    unread_count = models.PositiveIntegerField(_('Unread count'), default=0)
    favicon = models.ImageField(_('Favicon'), upload_to='favicons', null=True,
                                blank=True, storage=OverwritingStorage())
    img_safe = models.BooleanField(_('Display images by default'),
                                   default=False)

    def __unicode__(self):
        return u'%s' % self.name

    class Meta:
        ordering = ('name',)

    def get_absolute_url(self):
        return reverse('feeds:feed', args=[self.id])

    def save(self, *args, **kwargs):
        feed_created = self.pk is None
        super(Feed, self).save(*args, **kwargs)
        unique, created = UniqueFeed.objects.get_or_create(url=self.url)
        if feed_created or created:
            try:
                details = self.job_details
            except JobNotFound:
                details = {}
            enqueue(update_feed, kwargs={
                'url': self.url,
                'subscribers': details.get('subscribers', 1),
                'backoff_factor': details.get('backoff_factor', 1),
                'error': details.get('error'),
                'link': details.get('link'),
                'title': details.get('title'),
                'hub': details.get('hub'),
            }, queue='high', timeout=20)
            if not settings.TESTS:
                enqueue_favicon(unique.url)

    @property
    def media_safe(self):
        return self.img_safe

    def favicon_img(self):
        if not self.favicon:
            return ''
        return format_html(
            '<img src="{0}" width="16" height="16" />', self.favicon.url)

    def update_unread_count(self):
        self.unread_count = self.entries.filter(read=False).count()
        self.save(update_fields=['unread_count'])

    @property
    def color(self):
        md = hashlib.md5()
        md.update(self.url.encode('utf-8'))
        index = int(md.hexdigest()[0], 16)
        index = index * len(COLORS) // 16
        return COLORS[index][0]

    def error_display(self):
        if self.muted:
            key = self.error
        else:
            key = str(self.job_details['error'])
        return UniqueFeed.MUTE_DICT.get(key, _('Error'))


class EntryManager(models.Manager):
    def unread(self):
        return self.filter(read=False).count()


class Entry(models.Model):
    """An entry is a cached feed item"""
    feed = models.ForeignKey(Feed, verbose_name=_('Feed'), null=True,
                             blank=True, related_name='entries')
    title = models.CharField(_('Title'), max_length=255)
    subtitle = models.TextField(_('Abstract'))
    link = URLField(_('URL'), db_index=True)
    author = models.CharField(_('Author'), max_length=1023, blank=True)
    date = models.DateTimeField(_('Date'), db_index=True)
    guid = URLField(_('GUID'), db_index=True, blank=True)
    # The User FK is redundant but this may be better for performance and if
    # want to allow user input.
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             verbose_name=(_('User')), related_name='entries')
    # Mark something as read or unread
    read = models.BooleanField(_('Read'), default=False, db_index=True)
    # Read later: store the URL
    read_later_url = URLField(_('Read later URL'), blank=True)
    starred = models.BooleanField(_('Starred'), default=False, db_index=True)
    broadcast = models.BooleanField(_('Broadcast'), default=False,
                                    db_index=True)

    objects = EntryManager()

    class Meta:
        # Display most recent entries first
        ordering = ('-date', '-id')
        verbose_name_plural = 'entries'
        index_together = (
            ('user', 'date'),
            ('user', 'read'),
            ('user', 'starred'),
            ('user', 'broadcast'),
        )

    ELEMENTS = (
        feedparser._HTMLSanitizer.acceptable_elements |
        feedparser._HTMLSanitizer.mathml_elements |
        feedparser._HTMLSanitizer.svg_elements |
        set(['iframe', 'object', 'embed', 'script'])
    ) - set(['font'])
    ATTRIBUTES = (
        feedparser._HTMLSanitizer.acceptable_attributes |
        feedparser._HTMLSanitizer.mathml_attributes |
        feedparser._HTMLSanitizer.svg_attributes
    ) - set(['id', 'class'])
    CSS_PROPERTIES = feedparser._HTMLSanitizer.acceptable_css_properties

    def __unicode__(self):
        return u'%s' % self.title

    @property
    def hex_pk(self):
        value = hex(struct.unpack("L", struct.pack("l", self.pk))[0])
        if value.endswith("L"):
            value = value[:-1]
        return value[2:].zfill(16)

    def sanitized_title(self):
        if self.title:
            return unescape_entities(bleach.clean(self.title, tags=[],
                                                  strip=True))
        return _('(No title)')

    @property
    def content(self):
        if not hasattr(self, '_content'):
            if self.subtitle:
                xml = lxml.html.fromstring(self.subtitle)
                try:
                    xml.make_links_absolute(self.feed.url)
                except ValueError as e:
                    if e.args[0] != 'Invalid IPv6 URL':
                        raise
                self._content = lxml.html.tostring(xml)
            else:
                self._content = self.subtitle
        return self._content

    def sanitized_content(self):
        return bleach.clean(
            self.content,
            tags=self.ELEMENTS,
            attributes=self.ATTRIBUTES,
            styles=self.CSS_PROPERTIES,
            strip=True,
        )

    def sanitized_nomedia_content(self):
        return bleach.clean(
            self.content,
            tags=self.ELEMENTS - set(['img', 'audio', 'video', 'iframe',
                                      'object', 'embed', 'script', 'source']),
            attributes=self.ATTRIBUTES,
            styles=self.CSS_PROPERTIES,
            strip=True,
        )

    def get_absolute_url(self):
        return reverse('feeds:item', args=[self.id])

    def link_domain(self):
        return urlparse.urlparse(self.link).netloc

    def read_later_domain(self):
        netloc = urlparse.urlparse(self.read_later_url).netloc
        return netloc.replace('www.', '')

    def tweet(self):
        return u"{title} — {link}".format(
            title=self.title, link=self.link)

    def read_later(self):
        """Adds this item to the user's read list"""
        user = self.user
        if not user.read_later:
            return
        getattr(self, 'add_to_%s' % self.user.read_later)()

    def add_to_readitlater(self):
        url = 'https://readitlaterlist.com/v2/add'
        data = json.loads(self.user.read_later_credentials)
        data.update({
            'apikey': settings.API_KEYS['readitlater'],
            'url': self.link,
            'title': self.title,
        })
        # The readitlater API doesn't return anything back
        requests.post(url, data=data)

    def add_to_readability(self):
        url = 'https://www.readability.com/api/rest/v1/bookmarks'
        client = self.oauth_client('readability')
        params = {'url': self.link}
        response, data = client.request(url, method='POST',
                                        body=urllib.urlencode(params))
        response, data = client.request(response['location'], method='GET')
        url = 'https://www.readability.com/articles/%s'
        self.read_later_url = url % json.loads(data)['article']['id']
        self.save(update_fields=['read_later_url'])

    def add_to_instapaper(self):
        url = 'https://www.instapaper.com/api/1/bookmarks/add'
        client = self.oauth_client('instapaper')
        params = {'url': self.link}
        response, data = client.request(url, method='POST',
                                        body=urllib.urlencode(params))
        url = 'https://www.instapaper.com/read/%s'
        url = url % json.loads(data)[0]['bookmark_id']
        self.read_later_url = url
        self.save(update_fields=['read_later_url'])

    def oauth_client(self, service):
        service_settings = getattr(settings, service.upper())
        consumer = oauth.Consumer(service_settings['CONSUMER_KEY'],
                                  service_settings['CONSUMER_SECRET'])
        creds = json.loads(self.user.read_later_credentials)
        token = oauth.Token(key=creds['oauth_token'],
                            secret=creds['oauth_token_secret'])
        client = oauth.Client(consumer, token)
        client.set_signature_method(oauth.SignatureMethod_HMAC_SHA1())
        return client

    def current_year(self):
        return self.date.year == timezone.now().year


def pubsubhubbub_update(notification, request, links, **kwargs):
    url = None
    # Try the header links first
    if links is not None:
        for link in links:
            if link['rel'] == 'self':
                url = link['url']
                break

    notification = feedparser.parse(notification)

    # Fallback to feed links if no header link found
    if url is None:
        for link in notification.feed.get('links', []):
            if link['rel'] == 'self':
                url = link['href']
                break

    if url is None:
        return

    entries = filter(
        None,
        [UniqueFeedManager.entry_data(
            entry, notification) for entry in notification.entries]
    )
    if len(entries):
        enqueue(store_entries, args=[url, entries], queue='store')
updated.connect(pubsubhubbub_update)


class FaviconManager(models.Manager):
    def update_favicon(self, url, force_update=False):
        if not url:
            return
        parsed = list(urlparse.urlparse(url))
        if not parsed[0].startswith('http'):
            return
        favicon, created = self.get_or_create(url=url)
        feeds = Feed.objects.filter(url=url, favicon='')
        if (not created and not force_update) and favicon.favicon:
            # Still, add to existing
            favicon_urls = list(self.filter(url=url).exclude(
                favicon='').values_list('favicon', flat=True))
            if not favicon_urls:
                return favicon

            if not feeds.exists():
                return

            feeds.update(favicon=favicon_urls[0])
            return favicon

        ua = {'User-Agent': FAVICON_FETCHER}

        try:
            link = get_job(url).get('link')
        except JobNotFound:
            link = cache.get(u'feed_link:{0}'.format(url))

        if link is None:
            # TODO maybe re-fetch feed
            return favicon

        try:
            page = requests.get(link, headers=ua, timeout=10).content
        except (requests.RequestException, LocationParseError, socket.timeout,
                DecodeError, ConnectionError):
            return favicon
        if not page:
            return favicon

        try:
            icon_path = lxml.html.fromstring(page.lower()).xpath(
                '//link[@rel="icon" or @rel="shortcut icon"]/@href'
            )
        except ParserError:
            return favicon

        if not icon_path:
            parsed[2] = '/favicon.ico'  # 'path' element
            icon_path = [urlparse.urlunparse(parsed)]
        if not icon_path[0].startswith('http'):
            parsed[2] = icon_path[0]
            parsed[3] = parsed[4] = parsed[5] = ''
            icon_path = [urlparse.urlunparse(parsed)]
        try:
            response = requests.get(icon_path[0], headers=ua, timeout=10)
        except requests.RequestException:
            return favicon
        if response.status_code != 200:
            return favicon

        icon_file = ContentFile(response.content)
        icon_type = magic.from_buffer(response.content)
        if 'PNG' in icon_type:
            ext = 'png'
        elif ('MS Windows icon' in icon_type or
              'Claris clip art' in icon_type):
            ext = 'ico'
        elif 'GIF' in icon_type:
            ext = 'gif'
        elif 'JPEG' in icon_type:
            ext = 'jpg'
        elif 'PC bitmap' in icon_type:
            ext = 'bmp'
        elif 'TIFF' in icon_type:
            ext = 'tiff'
        elif icon_type == 'data':
            ext = 'ico'
        elif ('HTML' in icon_type or
              icon_type == 'empty' or
              'Photoshop' in icon_type or
              'ASCII' in icon_type or
              'XML' in icon_type or
              'Unicode text' in icon_type or
              'SGML' in icon_type or
              'PHP' in icon_type or
              'very short file' in icon_type or
              'gzip compressed data' in icon_type or
              'ISO-8859 text' in icon_type or
              'Lotus' in icon_type or
              'SVG' in icon_type or
              'Sendmail frozen' in icon_type or
              'GLS_BINARY_LSB_FIRST' in icon_type or
              'PDF' in icon_type or
              'PCX' in icon_type):
            logger.debug("Ignored content type for %s: %s" % (link, icon_type))
            return favicon
        else:
            logger.info("Unknown content type for %s: %s" % (link, icon_type))
            favicon.delete()
            return

        filename = '%s.%s' % (urlparse.urlparse(favicon.url).netloc, ext)
        favicon.favicon.save(filename, icon_file)

        for feed in feeds:
            feed.favicon.save(filename, icon_file)
        return favicon


class Favicon(models.Model):
    url = URLField(_('URL'), db_index=True, unique=True)
    favicon = models.FileField(upload_to='favicons', blank=True,
                               storage=OverwritingStorage())

    objects = FaviconManager()

    def __unicode__(self):
        return u'Favicon for %s' % self.url

    def favicon_img(self):
        if not self.favicon:
            return '(None)'
        return '<img src="%s">' % self.favicon.url
    favicon_img.allow_tags = True
