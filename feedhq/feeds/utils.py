import datetime
import feedparser
import logging
import lxml.html
import pytz
import requests
import socket
import time
import urllib2
import urlparse

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from django_push.subscriber.models import Subscription

from .. import __version__


USER_AGENT = 'FeedHQ/%s +https://github.org/feedhq/feedhq' % __version__
LINK_CHECKER = USER_AGENT + (' (link checker) - https://github.com/feedhq/'
                             'feedhq/wiki/User-Agent')

logger = logging.getLogger('feedupdater')


class FeedUpdater(object):

    def __init__(self, url, agent=' (1 subscriber)', feedparser=feedparser):
        self.url = url
        self.feedparser = feedparser
        self.updated = {}
        self.feeds = None
        feedparser.USER_AGENT = (USER_AGENT + agent + ' - https://github.com/f'
                                 'eedhq/feedhq/wiki/User-Agent')

    def update(self, use_etags=True):
        self.get_feeds()
        self.get_entries(use_etags)
        self.add_entries_to_feeds()
        self.handle_updated()
        self.remove_old_stuff()
        self.update_counts()

    def get_feeds(self):
        if self.feeds is None:
            from .models import Feed
            self.feeds = Feed.objects.filter(url=self.url, muted=False)

    def get_entries(self, use_etags=True):
        """Populates self.entries and self.updated
        self.entries: a list of Entry objects, parsed from self.url
        self.updated: a dict of values to push to self.feeds
        """
        from .models import Entry
        socket.setdefaulttimeout(5)  # aggressive but otherwise
                                     # it can take ages
        feed = self.feeds[0]
        if use_etags and feed.modified:
            modified = time.localtime(float(feed.modified))
            parsed_feed = self.feedparser.parse(feed.url, etag=feed.etag,
                                                modified=modified)
        else:
            parsed_feed = self.feedparser.parse(feed.url)

        if not 'status' in parsed_feed:
            logger.debug("No status in parsed feed, %s: %s" % (feed.pk,
                                                               feed.url))
            if feed.failed_attempts >= 20:
                logger.info("Feed failed 20 times, muting %s: %s" % (feed.pk,
                                                                     feed.url))
                self.feeds.update(muted=True)
            self.feeds.filter(url=feed.url).update(
                failed_attempts=F('failed_attempts') + 1
            )
            self.entries = []
            return
        self.feeds.update(failed_attempts=0)

        if parsed_feed.status == 301:  # permanent redirect
            self.updated['url'] = parsed_feed.href

        if parsed_feed.status == 410:  # Gone
            logger.info("Feed gone, %s: %s" % (feed.pk, feed.url))
            self.updated['muted'] = True
            self.entries = []
            return

        if parsed_feed.status == 304:  # Not modified
            logger.debug("Feed not modified, %s" % feed.url)
            self.entries = []
            return

        if ('link' in parsed_feed.feed and
            not feed.link == parsed_feed.feed.link):
            self.updated['link'] = parsed_feed.feed.link

        if ('title' in parsed_feed.feed and
            not feed.title == parsed_feed.feed.title):
            self.updated['title'] = parsed_feed.feed.title

        if 'etag' in parsed_feed:
            self.updated['etag'] = parsed_feed.etag
        if 'modified_parsed' in parsed_feed:
            timed = time.mktime(parsed_feed.modified_parsed)
            self.updated['modified'] = '%s' % timed

        if 'links' in parsed_feed.feed:
            for link in parsed_feed.feed.links:
                if link.rel == 'hub':
                    self.handle_hub(parsed_feed.href, link.href)

        self.entries = []
        for entry in parsed_feed.entries:
            if not 'link' in entry:
                continue
            title = entry.title if 'title' in entry else '(No title)'
            if len(title) > 255:
                title = title[:252] + '...'
            parsed_entry = Entry(title=title)
            if 'description' in entry:
                parsed_entry.subtitle = entry.description
            if 'summary' in entry:
                parsed_entry.subtitle = entry.summary
            if 'content' in entry:  # this overrides the summary
                if entry.content:
                    parsed_entry.subtitle = ''
                    for content in entry.content:
                        parsed_entry.subtitle += content.value

            parsed_entry.subtitle = self.clean_content(
                parsed_entry.subtitle,
            )

            parsed_entry.link = entry.link
            if 'guid' in entry:
                parsed_guid = urlparse.urlparse(entry.guid)
                parsed_link = urlparse.urlparse(parsed_feed.feed.link)
                if (parsed_guid.scheme in ('http', 'https') and
                    parsed_guid.netloc == parsed_link.netloc):
                    parsed_entry.guid = entry.guid

            if not parsed_entry.id:
                # Update some fields only if the entry is a new one
                parsed_entry.date = self.get_date(entry)

            self.entries.append(parsed_entry)

    def handle_hub(self, topic_url, hub_url):
        """
        Initiates a PubSubHubbub subscription and
        renews the lease if necessary.
        """
        if settings.DEBUG or settings.TESTS:
            # Do not use PubSubHubbub on local development
            return

        subscriptions = Subscription.objects.filter(topic=topic_url)
        if not subscriptions.exists():
            logger.info("Subscribing to %s: %s" % (topic_url, hub_url))
            subscriptions = [Subscription.objects.subscribe(topic_url,
                                                            hub=hub_url)]

        for subscription in subscriptions:
            if subscription.lease_expiration is None:
                continue

            if subscription.lease_expiration < timezone.now():
                logger.info("Renewing lease for %s: %s" % (topic_url, hub_url))
                try:
                    subscription = Subscription.objects.subscribe(
                        subscription.topic,
                        subscription.hub
                    )
                except urllib2.URLError:
                    pass

    def get_date(self, entry):
        if 'published_parsed' in entry and entry.published_parsed is not None:
            field = entry.published_parsed
        elif 'updated_parsed' in entry and entry.updated_parsed is not None:
            field = entry.updated_parsed
        else:
            field = None

        if field is None:
            entry_date = timezone.now()
        else:
            entry_date = timezone.make_aware(
                datetime.datetime(*field[:6]),
                pytz.utc,
            )
            # Sometimes entries are published in the future. If they're
            # published, it's probably safe to adjust the date.
            if entry_date > timezone.now():
                entry_date = timezone.now()
        return entry_date

    @transaction.commit_on_success
    def add_entries_to_feeds(self):
        from .models import Entry
        for entry in self.entries:
            for feed in self.feeds:
                treshold = feed.get_treshold()
                if treshold is not None and entry.date < treshold:
                    # Skipping, it's too old
                    continue

                if not entry.link:
                    params = {'title__iexact': entry.title, 'feed': feed}
                else:
                    params = {'link__iexact': entry.link, 'feed': feed}

                try:
                    db_entry = Entry.objects.get(**params)
                except Entry.DoesNotExist:
                    db_entry = entry
                except Entry.MultipleObjectsReturned:
                    multiple = Entry.objects.filter(**params).order_by('date')
                    db_entry = multiple[0]
                    for e in multiple[1:]:
                        e.delete()

                if db_entry.permalink:
                    entry.permalink = db_entry.permalink
                else:
                    if entry.permalink:
                        db_entry.permalink = entry.permalink
                    elif not settings.TESTS:
                        # Try to use guid if possible
                        if hasattr(entry, 'guid'):
                            ua = {'User-Agent': LINK_CHECKER}
                            try:
                                response = requests.head(entry.guid,
                                                         headers=ua,
                                                         allow_redirects=True)
                            except requests.ConnectionError:
                                pass
                            else:
                                if response.status_code == 200:
                                    resolved = response.url or ''
                                    db_entry.permalink = resolved
                                    entry.permalink = resolved

                if not db_entry.permalink:
                    db_entry.permalink = entry.permalink = entry.link

                db_entry.feed = feed
                db_entry.user = feed.category.user
                db_entry.save()
                feed.update_unread_count()

    def clean_content(self, content):
        page = lxml.html.fromstring('<div>%s</div>' % content)
        for element in page.iter('img'):
            if ('width="1"' in lxml.etree.tostring(element) or
                'width="0"' in lxml.etree.tostring(element)):
                # Tracking image -- deleting
                element.drop_tree()
        return lxml.etree.tostring(page)

    def handle_updated(self):
        self.feeds.update(**self.updated)

    def remove_old_stuff(self):
        """
        Gets rid of the `old` stuff, if the user doesn't want to keep the
        content in the archive.
        """
        from .models import Entry
        for feed in self.feeds:
            treshold = feed.get_treshold()
            if treshold is None:
                continue

            to_delete = Entry.objects.filter(feed=feed, date__lte=treshold)
            to_delete.delete()

    def update_counts(self):
        for feed in self.feeds:
            feed.update_unread_count()
