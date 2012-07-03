import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from raven import Client

from ....tasks import enqueue
from ...models import UniqueFeed
from ...tasks import update_feed

logger = logging.getLogger('feedupdater')


class Command(BaseCommand):
    """Updates the users' feeds"""

    def handle(self, *args, **kwargs):
        if args:
            pk = args[0]
            feed = UniqueFeed.objects.get(pk=pk)
            return update_feed(feed.url, use_etags=False)

        # This command is run every 5 minutes. Don't queue more than
        # 5/45 = a ninth of the total number of feeds.
        limit = UniqueFeed.objects.count() / 9

        uniques = UniqueFeed.objects.filter(
            muted=False,
        ).order_by('last_update')[:limit]

        for unique in uniques:
            try:
                if unique.should_update():
                    enqueue(update_feed, unique.url, timeout=20)
            except Exception:  # We don't know what to expect, and anyway
                               # we're reporting the exception
                if settings.DEBUG or not hasattr(settings, 'SENTRY_DSN'):
                    raise
                else:
                    client = Client(dsn=settings.SENTRY_DSN)
                    client.captureException()
        connection.close()
