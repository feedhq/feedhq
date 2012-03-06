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
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from django_push.subscriber.models import Subscription

from .. import __version__


USER_AGENT = 'FeedHQ/%s +https://github.org/brutasse/feedhq' % __version__

logger = logging.getLogger('feedupdater')


class FeedUpdater(object):

    def __init__(self, url, agent=' (1 subscriber)', feedparser=feedparser):
        self.url = url
        self.feedparser = feedparser
        self.updated = {}
        self.feeds = None
        feedparser.USER_AGENT = USER_AGENT
        feedparser.USER_AGENT += agent

    def update(self):
        self.get_feeds()
        self.get_entries()
        self.add_entries_to_feeds()
        self.handle_updated()
        self.remove_old_stuff()
        self.update_counts()
        self.grab_favicons()

    def get_feeds(self):
        if self.feeds is None:
            from .models import Feed
            self.feeds = Feed.objects.filter(url=self.url, muted=False)

    def get_entries(self):
        """Populates self.entries and self.updated
        self.entries: a list of Entry objects, parsed from self.url
        self.updated: a dict of values to push to self.feeds
        """
        from .models import Entry
        socket.setdefaulttimeout(5)  # aggressive but otherwise
                                     # it can take ages
        feed = self.feeds[0]
        if feed.modified:
            modified = time.localtime(float(feed.modified))
            parsed_feed = self.feedparser.parse(feed.url, etag=feed.etag,
                                                modified=modified)
        else:
            parsed_feed = self.feedparser.parse(feed.url)

        if not 'status' in parsed_feed:
            logger.info("No status in parsed feed, %s: %s" % (feed.pk,
                                                              feed.url))
            if feed.failed_attempts >= 20:
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

        if 'link' in parsed_feed.feed \
                and not feed.link == parsed_feed.feed.link:
            self.updated['link'] = parsed_feed.feed.link

        if 'title' in parsed_feed.feed \
                and not feed.title == parsed_feed.feed.title:
            self.updated['title'] = parsed_feed.feed.title

        if 'etag' in parsed_feed:
            self.updated['etag'] = parsed_feed.etag
        if 'modified' in parsed_feed:
            self.updated['modified'] = '%s' % time.mktime(parsed_feed.modified)

        if 'links' in parsed_feed.feed:
            for link in parsed_feed.feed.links:
                if link.rel == 'hub':
                    self.handle_hub(parsed_feed.href, link.href)

        self.entries = []
        for entry in parsed_feed.entries:
            if not 'link' in entry:
                continue
            title = entry.title
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

            if not parsed_entry.id:
                # Update some fields only if the entry is a new one
                parsed_entry.date = self.get_date(entry)

            if (entry.link and
                'feedproxy.google.com' in entry.link and
                not parsed_entry.permalink):
                # Handling the FeedBurner redirection on behalf of the user
                response = requests.head(entry.link)
                parsed_entry.permalink = response.headers['Location']
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

        tomorrow = timezone.now() + datetime.timedelta(days=1)
        for subscription in subscriptions:
            if subscription.lease_expiration is None:
                continue

            if subscription.lease_expiration < tomorrow:
                logger.info("Renewing lease for %s: %s" % (topic_url, hub_url))
                try:
                    subscription = Subscription.objects.subscribe(
                        subscription.topic,
                        subscription.hub
                    )
                except urllib2.URLError:
                    pass

    def get_date(self, entry):
        if 'updated_parsed' in entry and entry.updated_parsed is not None:
            entry_date = timezone.make_aware(
                datetime.datetime(*entry.updated_parsed[:6]),
                pytz.utc,
            )
            # Sometimes entries are published in the future. If they're
            # published, it's probably safe to adjust the date.
            if entry_date > timezone.now():
                entry_date = timezone.now()
        else:
            entry_date = timezone.now()
        return entry_date

    @transaction.commit_on_success
    def add_entries_to_feeds(self):
        from .models import Entry
        for feed in self.feeds:
            treshold = feed.get_treshold()
            for entry in self.entries:
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

                db_entry.feed = feed
                db_entry.user = feed.category.user
                db_entry.save()
                feed.update_unread_count()

    def clean_content(self, content):
        page = lxml.html.fromstring('<div>%s</div>' % content)
        for element in page.iter('img'):
            if 'width="1"' in lxml.etree.tostring(element) \
                    or 'width="0"' in lxml.etree.tostring(element):
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

    def grab_favicons(self):
        if settings.TESTS:
            return

        if all((f.favicon for f in self.feeds)):
            return

        if any((f.favicon for f in self.feeds)):
            for f in self.feeds:
                if f.favicon:
                    fav = f.favicon
                    continue

            self.feeds.update(favicon=fav)
            return

        if self.feeds[0].no_favicon == True:
            return

        if not self.feeds[0].link:
            return

        page = self.fetch_or_no_favicon(self.feeds[0].link)
        if page is None:
            return

        icon_path = lxml.html.fromstring(page.lower()).xpath(
            '//link[@rel="icon" or @rel="shortcut icon"]/@href')

        if not icon_path:
            if self.feeds[0].no_favicon:
                return
            url = urlparse.urlparse(self.feeds[0].link)
            icon_path = ['%s://%s/favicon.ico' % (url.scheme, url.netloc)]

        if not icon_path[0].startswith('http'):
            icon_path[0] = self.feeds[0].link + icon_path[0]

        icon_content = self.fetch_or_no_favicon(icon_path[0])
        if icon_content is None:
            return

        icon_file = ContentFile(icon_content)
        for f in self.feeds:  # FIXME select_for_update
            f.favicon.save('favicons/%s.ico' % f.pk, icon_file)

    def fetch_or_no_favicon(self, url):
        try:
            return urllib2.urlopen(url).read()
        except (urllib2.HTTPError, urllib2.URLError):
            self.feeds.update(no_favicon=True)
