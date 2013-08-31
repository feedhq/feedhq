import logging

from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django_push.subscriber.models import Subscription
from rache import schedule_job
from rq.timeouts import JobTimeoutException

from ..utils import get_redis_connection

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
                     backoff_factor=backoff_factor,
                     connection=get_redis_connection())


def read_later(entry_pk):
    from .models import Entry
    Entry.objects.get(pk=entry_pk).read_later()


def update_favicon(feed_url, force_update=False):
    from .models import Favicon
    Favicon.objects.update_favicon(feed_url, force_update=force_update)


def subscribe(topic_url, hub_url):
    Subscription.objects.subscribe(topic_url, hub_url)


def store_entries(feed_url, entries):
    from .models import Entry, Feed
    guids = set([entry['guid'] for entry in entries])

    query = Q(feed__url=feed_url)

    # When we have dates, filter the query to avoid returning the whole dataset
    date_generated = any([e.pop('date_generated') for e in entries])
    if not date_generated:
        earliest = min([entry['date'] for entry in entries])
        query &= Q(date__gte=earliest - timedelta(days=1))

    filter_by_title = len(guids) == 1 and len(entries) > 1
    if filter_by_title:
        # All items have the same guid. Query by title instead.
        titles = set([entry['title'] for entry in entries])
        query &= Q(title__in=titles)
    else:
        query &= Q(guid__in=guids)
    existing = Entry.objects.filter(query).values('guid', 'title', 'feed_id')

    existing_guids = defaultdict(set)
    existing_titles = defaultdict(set)
    for entry in existing:
        existing_guids[entry['feed_id']].add(entry['guid'])
        if filter_by_title:
            existing_titles[entry['feed_id']].add(entry['title'])

    feeds = Feed.objects.filter(
        url=feed_url, user__is_suspended=False).values('pk', 'user_id')

    create = []
    update_unread_counts = set()
    for feed in feeds:
        for entry in entries:
            if (
                not filter_by_title and
                entry['guid'] in existing_guids[feed['pk']]
            ):
                continue
            if (
                filter_by_title and
                entry['title'] in existing_titles[feed['pk']]
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
