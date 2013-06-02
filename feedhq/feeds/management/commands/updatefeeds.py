import logging

from rache import pending_jobs

from ....tasks import enqueue
from ...models import UniqueFeed
from ...tasks import update_feed
from . import SentryCommand

logger = logging.getLogger(__name__)


class Command(SentryCommand):
    """Updates the users' feeds"""

    def handle_sentry(self, *args, **kwargs):
        if args:
            pk = args[0]
            feed = UniqueFeed.objects.get(pk=pk)
            return update_feed(
                feed.url, etag=feed.etag, last_modified=feed.modified,
                subscribers=feed.subscribers,
                request_timeout=feed.request_timeout,
                backoff_factor=feed.backoff_factor, error=feed.error,
                link=feed.link, title=feed.title, hub=feed.hub,
            )

        ratio = UniqueFeed.UPDATE_PERIOD // 5
        limit = max(
            1, UniqueFeed.objects.filter(muted=False).count() // ratio)
        jobs = pending_jobs(limit=limit,
                            reschedule_in=UniqueFeed.UPDATE_PERIOD * 60)
        for job in jobs:
            url = job.pop('id')
            job.pop('last_update', None)
            enqueue(update_feed, args=[url], kwargs=job,
                    timeout=UniqueFeed.TIMEOUT_BASE * job['backoff_factor'])
