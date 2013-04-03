import logging

from collections import defaultdict

from django_push.subscriber.models import Subscription
from rq.timeouts import JobTimeoutException

from ..tasks import raven

logger = logging.getLogger('feedupdater')


@raven
def update_feed(url, etag=None, last_modified=None, subscribers=1,
                request_timeout=10, backoff_factor=1, error=None, link=None,
                title=None, hub=None):
    from .models import UniqueFeed
    try:
        UniqueFeed.objects.update_feed(
            url, etag=etag, last_modified=last_modified,
            subscribers=subscribers, request_timeout=request_timeout,
            backoff_factor=backoff_factor, previous_error=error, link=link,
            title=title, hub=hub)
    except JobTimeoutException:
        feed = UniqueFeed.objects.get(url=url)
        feed.backoff()
        feed.save()
        logger.debug("Job timed out, backing off %s to %s" % (
            feed.url, feed.backoff_factor,
        ))


@raven
def read_later(entry_pk):
    from .models import Entry
    Entry.objects.get(pk=entry_pk).read_later()


@raven
def update_favicon(feed_url):
    from .models import Favicon
    Favicon.objects.update_favicon(feed_url)


@raven
def subscribe(topic_url, hub_url):
    Subscription.objects.subscribe(topic_url, hub_url)


@raven
def store_entries(feed_url, entries):
    from .models import Entry, Feed
    links = set([entry['link'] for entry in entries])
    existing = Entry.objects.filter(feed__url=feed_url,
                                    link__in=links).values('link', 'feed_id')
    existing_map = defaultdict(set)
    for entry in existing:
        existing_map[entry['feed_id']].add(entry['link'])
    feeds = Feed.objects.filter(url=feed_url).select_related(
        'category__user').values('pk', 'category__user__pk')

    create = []
    update_unread_counts = set()
    for feed in feeds:
        for entry in entries:
            if entry['link'] in existing_map[feed['pk']]:
                continue
            create.append(Entry(user_id=feed['category__user__pk'],
                                feed_id=feed['pk'], **entry))
            update_unread_counts.add(feed['pk'])

    if create:
        Entry.objects.bulk_create(create)

    for pk in update_unread_counts:
        Feed.objects.filter(pk=pk).update(
            unread_count=Entry.objects.filter(feed_id=pk, read=False).count())
