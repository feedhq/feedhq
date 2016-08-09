import logging

from rache import pending_jobs
from rq import Queue

from . import SentryCommand
from ...models import UniqueFeed
from ...tasks import update_feed
from ....tasks import enqueue
from ....utils import get_redis_connection

logger = logging.getLogger(__name__)


class Command(SentryCommand):
    help = "Updates the users' feeds"

    def add_arguments(self, parser):
        parser.add_argument('feed_id', nargs='*', type=int)

    def handle_sentry(self, *args, **kwargs):
        if args:
            pk = args[0]
            feed = UniqueFeed.objects.get(pk=pk)
            data = feed.job_details
            return update_feed(
                feed.url, etag=data.get('etag'), modified=data.get('modified'),
                subscribers=data.get('subscribers', 1),
                backoff_factor=data['backoff_factor'], error=data.get('error'),
                link=data.get('link'), title=data.get('title'),
                hub=data.get('hub'),
            )

        ratio = UniqueFeed.UPDATE_PERIOD // 5
        limit = max(
            1, UniqueFeed.objects.filter(muted=False).count() // ratio) * 2

        # Avoid queueing if the default or store queue is already full
        conn = get_redis_connection()
        for name in ['default', 'store']:
            queue = Queue(name=name, connection=conn)
            if queue.count > limit:
                logger.info(
                    "{0} queue longer than limit, skipping update "
                    "({1} > {2})".format(name, queue.count, limit))
                return

        jobs = pending_jobs(limit=limit,
                            reschedule_in=UniqueFeed.UPDATE_PERIOD * 60,
                            connection=get_redis_connection())
        for job in jobs:
            url = job.pop('id')
            job.pop('last_update', None)
            enqueue(update_feed, args=[url], kwargs=job,
                    timeout=UniqueFeed.TIMEOUT_BASE * job.get(
                        'backoff_factor', 1))
