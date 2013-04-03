import os

from django.conf import settings
from django.core.management.base import BaseCommand
from raven import Client

from ...models import UniqueFeed


class Command(BaseCommand):
    """Updates the users' feeds"""

    def handle(self, *args, **kwargs):
        try:
            unsubscribed = UniqueFeed.objects.raw(
                """
                select id from feeds_uniquefeed u where not exists (
                    select 1 from feeds_feed f where f.url = u.url
                )
                """)
            pks = [u.pk for u in unsubscribed]
            UniqueFeed.objects.filter(pk__in=pks).delete()
        except Exception:
            if settings.DEBUG or not 'SENTRY_DSN' in os.environ:
                raise
            client = Client()
            client.captureException()
