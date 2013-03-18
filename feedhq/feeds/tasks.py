import logging

from django.db import DatabaseError

from django_push.subscriber.models import Subscription
from rq.timeouts import JobTimeoutException

from ..tasks import raven, enqueue

logger = logging.getLogger('feedupdater')


@raven
def update_feed(feed_url, use_etags=True):
    from .models import UniqueFeed
    try:
        UniqueFeed.objects.update_feed(feed_url, use_etags)
    except JobTimeoutException:
        feed = UniqueFeed.objects.get(url=feed_url)
        feed.backoff()
        feed.save()
        logger.debug("Job timed out, backing off %s to %s" % (
            feed.url, feed.backoff_factor,
        ))


@raven
def read_later(entry_pk):
    from .models import Entry  # circular imports
    Entry.objects.get(pk=entry_pk).read_later()


@raven
def update_unique_feed(feed_url):
    from .models import UniqueFeed, Feed
    feed, created = UniqueFeed.objects.get_or_create(
        url=feed_url,
        defaults={'subscribers': 1},
    )
    if created:
        enqueue(update_favicon, args=[feed_url], queue='favicons')
    else:
        feed.subscribers = Feed.objects.filter(url=feed_url).count()
        try:
            feed.save(update_fields=['subscribers'])
        except DatabaseError as e:
            # Possible concurrent update with a different UniqueFeed
            if "Save with update_fields did not affect any rows" not in str(e):
                raise


@raven
def update_favicon(feed_url):
    from .models import Favicon
    Favicon.objects.update_favicon(feed_url)


@raven
def subscribe(topic_url, hub_url):
    Subscription.objects.subscribe(topic_url, hub_url)
