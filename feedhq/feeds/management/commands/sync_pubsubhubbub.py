import logging
import os

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django_push.subscriber.models import Subscription
from raven import Client

from ...models import UniqueFeed
from . import SentryCommand

logger = logging.getLogger(__name__)


class Command(SentryCommand):
    """Updates PubSubHubbub subscriptions"""

    def handle_sentry(self, *args, **kwargs):
        missing = list(UniqueFeed.objects.raw(
            """
            select id, url, hub from feeds_uniquefeed u where
                not exists (
                    select 1 from subscriber_subscription s
                    where
                        u.url = s.topic and
                        u.hub = s.hub
                ) and
                u.hub like 'http%%'
            """))
        if len(missing):
            logger.info("Subscribing to {0} feeds".format(len(missing)))
            for feed in missing:
                try:
                    Subscription.objects.subscribe(feed.url, hub=feed.hub)
                except Exception:
                    if settings.DEBUG or not 'SENTRY_DSN' in os.environ:
                        raise
                    client = Client()
                    client.captureException()

        extra = list(Subscription.objects.raw(
            """
            select * from subscriber_subscription s where not exists (
                select 1 from feeds_uniquefeed u
                where
                    u.url = s.topic and
                    u.hub = s.hub and
                    u.hub like 'http%%'
            )
            """))
        if len(extra):
            logger.info("Unsubscribing from {0} feeds".format(len(extra)))
            for subscription in extra:
                try:
                    subscription.unsubscribe()
                except Exception:
                    if settings.DEBUG or not 'SENTRY_DSN' in os.environ:
                        raise
                    client = Client()
                    client.captureException()

        expiring = Subscription.objects.filter(
            lease_expiration__lte=timezone.now() + timedelta(days=1))
        if len(expiring):
            logger.info("Renewing {0} subscriptions".format(len(expiring)))
            for subscription in expiring:
                try:
                    subscription.subscribe()
                except Exception:
                    if settings.DEBUG or not 'SENTRY_DSN' in os.environ:
                        raise
                    client = Client()
                    client.captureException()
