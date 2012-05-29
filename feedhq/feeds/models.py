import datetime
import json
import lxml
import oauth2 as oauth
import urllib
import urlparse
import requests

from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from django_push.subscriber.signals import updated

from .tasks import update_feed
from .utils import FeedUpdater
from .. import __version__
from ..storage import OverwritingStorage
from ..tasks import enqueue

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


DURATIONS = (
        ('1day', _('One day')),
        ('2days', _('Two days')),
        ('1week', _('One week')),
        ('1month', _('One month')),
        ('1year', _('One year')),
        ('never', _('Never')),
)


TIMEDELTAS = {
    '1day': datetime.timedelta(days=1),
    '2days': datetime.timedelta(days=2),
    '1week': datetime.timedelta(weeks=1),
    '1month': datetime.timedelta(days=30),
    '1year': datetime.timedelta(days=365),
    #'never': None, # Implicit
}


class CategoryManager(models.Manager):

    def with_unread_counts(self):
        return self.values('id', 'name', 'slug', 'color').annotate(
            unread_count=models.Sum('feeds__unread_count'))


class Category(models.Model):
    """Used to sort our feeds"""
    name = models.CharField(_('Name'), max_length=50)
    slug = models.SlugField(_('Slug'), db_index=True)
    user = models.ForeignKey(User, verbose_name=_('User'),
                             related_name='categories')
    # Some day there will be drag'n'drop ordering
    order = models.PositiveIntegerField(blank=True, null=True)

    # Categories have nice cute colors
    color = models.CharField(_('Color'), max_length=50, choices=COLORS,
                             default='pale-green')

    # We delete the old entries after a certain while
    delete_after = models.CharField(
        _('Delete after'), max_length=50, choices=DURATIONS, default='1month',
        help_text=_("Period of time after which entries are deleted, whether "
                    "they've been read or not."),
    )

    objects = CategoryManager()

    def __unicode__(self):
        return u'%s' % self.name

    class Meta:
        ordering = ('order', 'name', 'id')
        verbose_name_plural = 'categories'

    def get_absolute_url(self):
        return reverse('feeds:category', args=[self.slug])


class Feed(models.Model):
    """A URL and some extra stuff"""
    name = models.CharField(_('Name'), max_length=255)
    url = models.URLField(_('URL'), verify_exists=False, max_length=1023)
    category = models.ForeignKey(
        Category, verbose_name=_('Category'), related_name='feeds',
        help_text=_('<a href="/category/add/">Add a category</a>'),
    )
    # The next 2 are RSS/ATOM attributes
    title = models.CharField(_('Title'), max_length=255)
    link = models.URLField(_('Link'), verify_exists=False, max_length=1023)
    # Mute a feed when we don't want the updates to show up in the timeline
    muted = models.BooleanField(_('Muted'), default=False,
                                help_text=_('Check this if you want to stop '
                                           'checking updates for this feed'))
    etag = models.CharField(_('Etag'), max_length=1023, null=True, blank=True)
    modified = models.CharField(_('Modified'), max_length=255, null=True,
                                blank=True)
    unread_count = models.PositiveIntegerField(_('Unread count'), default=0)
    favicon = models.ImageField(_('Favicon'), upload_to='favicons', null=True,
                                storage=OverwritingStorage())
    no_favicon = models.BooleanField(_('No favicon'), default=False)
    img_safe = models.BooleanField(_('Display images by default'),
                                   default=False)
    failed_attempts = models.IntegerField(_('Failed fetching attempts'),
                                          default=0)

    def __unicode__(self):
        return u'%s' % self.name

    class Meta:
        ordering = ('name',)

    def get_absolute_url(self):
        return reverse('feeds:feed', args=[self.id])

    def save(self, *args, **kwargs):
        update = self.pk is None
        super(Feed, self).save(*args, **kwargs)
        if update:
            if settings.TESTS:
                update_feed(self.url, use_etags=False)
            else:
                enqueue(update_feed, self.url, use_etags=False)

    def favicon_img(self):
        if not self.favicon:
            return ''
        return '<img src="%s" width="16" height="16" />' % self.favicon.url
    favicon_img.allow_tags = True

    def get_treshold(self):
        """Returns the date after which the entries can be ignored / deleted"""
        del_after = self.category.delete_after

        if del_after == 'never':
            return None
        return timezone.now() - TIMEDELTAS[del_after]

    def update_unread_count(self):
        self.unread_count = self.entries.filter(read=False).count()
        Feed.objects.filter(pk=self.pk).update(
            unread_count=self.unread_count,
        )


class EntryManager(models.Manager):
    def unread(self):
        return self.filter(read=False).count()


class Entry(models.Model):
    """An entry is a cached feed item"""
    feed = models.ForeignKey(Feed, verbose_name=_('Feed'),
                             related_name='entries')
    title = models.CharField(_('Title'), max_length=255)
    subtitle = models.TextField(_('Abstract'))
    link = models.URLField(_('URL'), verify_exists=False, max_length=1023)
    # We also have a permalink for feed proxies (like FeedBurner). If the link
    # points to feedburner, the redirection (=real feed link) is put here
    permalink = models.URLField(_('Permalink'), verify_exists=False,
                                max_length=1023, blank=True)
    date = models.DateTimeField(_('Date'), db_index=True)
    # The User FK is redundant but this may be better for performance and if
    # want to allow user input.
    user = models.ForeignKey(User, verbose_name=(_('User')),
                             related_name='entries')
    # Mark something as read or unread
    read = models.BooleanField(_('Read'), default=False, db_index=True)
    # Read later: store the URL
    read_later_url = models.URLField(_('Read later URL'), verify_exists=False,
                                 max_length=1023, blank=True)

    objects = EntryManager()

    def __unicode__(self):
        return u'%s' % self.title

    class Meta:
        # Display most recent entries first
        ordering = ('-date', 'title')
        verbose_name_plural = 'entries'

    def get_absolute_url(self):
        return reverse('feeds:item', args=[self.id])

    def get_link(self):
        if self.permalink:
            return self.permalink
        return self.link

    def link_domain(self):
        return urlparse.urlparse(self.get_link()).netloc

    def read_later_domain(self):
        netloc = urlparse.urlparse(self.read_later_url).netloc
        return netloc.replace('www.', '')

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
            'url': self.get_link(),
            'title': self.title,
        })
        # The readitlater API doesn't return anything back
        requests.post(url, data=data)

    def add_to_readability(self):
        url = 'https://www.readability.com/api/rest/v1/bookmarks'
        client = self.oauth_client('readability')
        params = {'url': self.get_link()}
        response, data = client.request(url, method='POST',
                                        body=urllib.urlencode(params))
        response, data = client.request(response['location'], method='GET')
        url = 'https://www.readability.com/articles/%s'
        self.read_later_url = url % json.loads(data)['article']['id']
        self.save()

    def add_to_instapaper(self):
        url = 'https://www.instapaper.com/api/1/bookmarks/add'
        client = self.oauth_client('instapaper')
        params = {'url': self.get_link()}
        response, data = client.request(url, method='POST',
                                        body=urllib.urlencode(params))
        url = 'https://www.instapaper.com/read/%s'
        url = url % json.loads(data)[0]['bookmark_id']
        self.read_later_url = url
        self.save()

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


def pubsubhubbub_update(notification, **kwargs):
    parsed = notification
    url = None
    for link in parsed.feed.links:
        if link['rel'] == 'self':
            url = link['href']
    if url is None:
        return
    updater = FeedUpdater(url)

    entries = []
    for entry in parsed.entries:
        if not 'link' in entry:
            continue
        e = Entry(title=entry.title)
        if 'description' in entry:
            e.subtitle = entry.description
        if 'summary' in entry:
            e.subtitle = entry.summary

        e.link = entry.link
        e.date = updater.get_date(entry)
        entries.append(e)

    updater.get_feeds()
    updater.entries = entries
    updater.add_entries_to_feeds()
updated.connect(pubsubhubbub_update)


def upload_favicon(instance, filename):
    netloc = urlparse.urlparse(instance.url).netloc
    return 'favicons/%s.png' % netloc


class FaviconManager(models.Manager):
    USER_AGENT = ('FeedHQ/%s +https://github.com/feedhq/feedhq (favicon '
                  'fetcher) - https://github.com/feedhq/feedhq/wiki/'
                  'User-Agent' % __version__)

    def update_favicon(self, link, force_update=False):
        parsed = list(urlparse.urlparse(link))
        favicon, created = self.get_or_create(url=link)
        if favicon.favicon and not force_update:
            return favicon

        ua = {'User-Agent': self.USER_AGENT}

        try:
            page = requests.get(link, headers=ua).content
        except requests.RequestException:
            return favicon
        if not page:
            return favicon

        icon_path = lxml.html.fromstring(page.lower()).xpath(
            '//link[@rel="icon" or @rel="shortcut icon"]/@href'
        )

        if not icon_path:
            parsed[2] = '/favicon.ico'  # 'path' element
            icon_path = [urlparse.urlunparse(parsed)]
        if not icon_path[0].startswith('http'):
            parsed[2] = icon_path[0]
            icon_path = [urlparse.urlunparse(parsed)]
        try:
            response = requests.get(icon_path[0], headers=ua)
        except requests.RequestException:
            return favicon
        if response.status_code != 200:
            return favicon
        if ('content-type' not in response.headers or
            not response.headers['content-type'].startswith('image/')):
            return favicon

        icon_file = ContentFile(response.content)
        favicon.favicon.save(upload_favicon(favicon, ''), icon_file)

        feeds = Feed.objects.filter(link=link)
        for feed in feeds:
            feed.favicon.save(upload_favicon(favicon, ''), icon_file)
        feeds.update(no_favicon=False)
        return favicon


class Favicon(models.Model):
    url = models.URLField(_('Domain URL'), db_index=True)
    favicon = models.FileField(upload_to=upload_favicon, blank=True,
                               storage=OverwritingStorage())

    objects = FaviconManager()

    def favicon_img(self):
        if not self.favicon:
            return '(None)'
        return '<img src="%s">' % self.favicon.url
    favicon_img.allow_tags = True
