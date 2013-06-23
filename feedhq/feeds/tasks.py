import json
import logging

from collections import defaultdict

from django.db.models import Q
from django_push.subscriber.models import Subscription
from rache import schedule_job
from rq.timeouts import JobTimeoutException

logger = logging.getLogger(__name__)


def update_feed(url, etag=None, modified=None, subscribers=1,
                request_timeout=10, backoff_factor=1, error=None, link=None,
                title=None, hub=None):
    from .models import UniqueFeed
    try:
        UniqueFeed.objects.update_feed(
            url, etag=etag, last_modified=modified,
            subscribers=subscribers, request_timeout=request_timeout,
            backoff_factor=backoff_factor, previous_error=error, link=link,
            title=title, hub=hub)
    except JobTimeoutException:
        backoff_factor = min(UniqueFeed.MAX_BACKOFF,
                             backoff_factor + 1)
        logger.debug("Job timed out, backing off %s to %s" % (
            url, backoff_factor,
        ))
        schedule_job(url, schedule_in=UniqueFeed.delay(backoff_factor),
                     backoff_factor=backoff_factor)


def read_later(entry_pk):
    from .models import Entry
    Entry.objects.get(pk=entry_pk).read_later()


def update_favicon(feed_url, force_update=False):
    from .models import Favicon
    Favicon.objects.update_favicon(feed_url, force_update=force_update)


def subscribe(topic_url, hub_url):
    Subscription.objects.subscribe(topic_url, hub_url)


def store_entries(feed_url, entries, json_format=False):
    from .models import Entry, Feed
    if json_format:
        entries = json.loads(entries)
    links = set([entry['link'] for entry in entries])
    guids = set([entry['guid'] for entry in entries])
    query = Q(feed__url=feed_url) & (Q(link__in=links) | Q(guid__in=guids))
    existing = Entry.objects.filter(query).values('link', 'guid', 'feed_id')
    existing_links = defaultdict(set)
    existing_guids = defaultdict(set)
    for entry in existing:
        existing_links[entry['feed_id']].add(entry['link'])
        if entry['guid']:
            existing_guids[entry['feed_id']].add(entry['guid'])

    feeds = Feed.objects.filter(
        url=feed_url, user__is_suspended=False).values('pk', 'user_id')

    create = []
    update_unread_counts = set()
    for feed in feeds:
        for entry in entries:
            if (
                entry['link'] in existing_links[feed['pk']] or
                entry['guid'] in existing_guids[feed['pk']]
            ):
                continue
            create.append(Entry(user_id=feed['user_id'],
                                feed_id=feed['pk'], **entry))
            update_unread_counts.add(feed['pk'])

    if create:
        Entry.objects.bulk_create(create)

    for pk in update_unread_counts:
        Feed.objects.filter(pk=pk).update(
            unread_count=Entry.objects.filter(feed_id=pk, read=False).count())
