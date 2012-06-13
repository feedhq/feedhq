from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from raven import Client

from ...models import Feed


class Command(BaseCommand):
    """Checks defunct feeds in case of resurrection."""

    def handle(self, *args, **kwargs):
        for feed in Feed.objects.filter(failed_attempts__gt=0, muted=True):
            try:
                feed.resurrect()
            except Exception:
                if settings.DEBUG or not hasattr(settings, 'SENTRY_DSN'):
                    raise
                client = Client(dsn=settings.SENTRY_DSN)
                client.captureException()
        connection.close()
