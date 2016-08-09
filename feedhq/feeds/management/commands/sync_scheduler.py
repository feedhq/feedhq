import logging

from more_itertools import chunked
from rache import delete_job, scheduled_jobs

from . import SentryCommand
from ...models import UniqueFeed
from ....utils import get_redis_connection

logger = logging.getLogger(__name__)


class Command(SentryCommand):
    """Syncs the UniqueFeeds and the scheduler:

        - removes scheduled feeds which are missing from uniquefeeds
        - adds missing uniquefeeds to the scheduler
    """

    def handle_sentry(self, *args, **kwargs):
        connection = get_redis_connection()
        existing_jobs = set(scheduled_jobs(connection=connection))
        target = set(UniqueFeed.objects.filter(muted=False).values_list(
            'url', flat=True))

        to_delete = existing_jobs - target
        if to_delete:
            logger.info(
                "Deleting %s jobs from the scheduler", len(to_delete))
            for job_id in to_delete:
                delete_job(job_id, connection=connection)

        to_add = target - existing_jobs
        if to_add:
            logger.info("Adding %s jobs to the scheduler", len(to_add))
            for chunk in chunked(to_add, 10000):
                uniques = UniqueFeed.objects.filter(url__in=chunk)
                for unique in uniques:
                    unique.schedule()
