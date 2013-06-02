import logging

from datetime import datetime

import pytz

from django.utils import timezone
from rache import scheduled_jobs, job_details

from ...models import UniqueFeed
from . import SentryCommand

logger = logging.getLogger(__name__)


class Command(SentryCommand):
    """Backs up the scheduler data to the database.

    Should be run as a low-frequency background job (twice a day, at most).
    """

    def handle_sentry(self, *args, **kwargs):
        existing_jobs = set(scheduled_jobs())
        for url in existing_jobs:
            details = job_details(url)
            attrs = {
                'title': '',
                'link': '',
                'etag': '',
                'modified': '',
                'error': '',
                'hub': '',
                'backoff_factor': 1,
                'subscribers': 1,
            }
            for key in attrs:
                if key in details:
                    attrs[key] = details[key]
            if 'last_update' in details:
                attrs['last_update'] = timezone.make_aware(
                    datetime.utcfromtimestamp(details['last_update']),
                    pytz.utc)
            UniqueFeed.objects.filter(url=url).update(**attrs)
