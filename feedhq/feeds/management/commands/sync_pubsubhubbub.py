import os

import structlog
from django.conf import settings
from django_push.subscriber.models import Subscription
from raven import Client

from . import SentryCommand

logger = structlog.get_logger(__name__)


class Command(SentryCommand):
    """Updates PubSubHubbub subscriptions"""

    def handle_sentry(self, *args, **kwargs):
        extra = list(Subscription.objects.raw(
            """
            select * from subscriber_subscription s where not exists (
                select 1 from feeds_uniquefeed u
                where u.url = s.topic
            ) and s.lease_expiration >= current_timestamp
            """))
        if len(extra):
            logger.info("unsubscribing from feeds", count=len(extra))
            for subscription in extra:
                try:
                    subscription.unsubscribe()
                except Exception:
                    if settings.DEBUG or 'SENTRY_DSN' not in os.environ:
                        raise
                    client = Client()
                    client.captureException()
