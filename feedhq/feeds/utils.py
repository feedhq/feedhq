import datetime
import logging
import lxml.html
import pytz
import urllib2
import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from django_push.subscriber.models import Subscription

from .. import __version__


USER_AGENT = (
    'FeedHQ/%s (https://github.com/feedhq/feedhq; %%s; https://github.com/'
    'feedhq/feedhq/wiki/User-Agent)'
) % __version__
FEED_CHECKER = USER_AGENT % 'feed checker'
FAVICON_FETCHER = USER_AGENT % 'favicon fetcher'

logger = logging.getLogger('feedupdater')


class FeedUpdater(object):
    def __init__(self, parsed, feeds):
        self.parsed = parsed
        self.feeds = feeds

    def update(self):
        self.get_entries()
        self.add_entries_to_feeds()
        self.remove_old_stuff()
        self.update_counts()

    def get_entries(self):
        """Populates self.entries: a list of Entry objects"""
        from .models import Entry
        self.entries = []
        for entry in self.parsed.entries:
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
                parsed_link = urlparse.urlparse(self.parsed.feed.link)
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
            logger.debug("Subscribing to %s: %s" % (topic_url, hub_url))
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
                if feed.muted:
                    continue
                treshold = feed.get_treshold()
                if treshold is not None and entry.date < treshold:
                    # Skipping, it's too old
                    continue

                if not entry.link:
                    params = {'title__iexact': entry.title, 'feed': feed}
                else:
                    params = {'link__iexact': entry.link, 'feed': feed}
                params['feed'] = feed

                create = False
                try:
                    db_entry = Entry.objects.get(**params)
                except Entry.DoesNotExist:
                    db_entry = entry
                    create = True
                except Entry.MultipleObjectsReturned:
                    multiple = Entry.objects.filter(**params).order_by('date')
                    db_entry = multiple[0]
                    for e in multiple[1:]:
                        e.delete()

                if db_entry.permalink:
                    entry.permalink = db_entry.permalink
                elif entry.permalink:
                    db_entry.permalink = entry.permalink

                if not db_entry.permalink:
                    db_entry.permalink = entry.permalink = entry.link

                db_entry.feed = feed
                db_entry.user = feed.category.user
                if create:
                    db_entry.pk = None
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
