import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from raven import Client

from ....tasks import enqueue
from ...models import UniqueFeed, Feed
from ...tasks import update_feed
from ...utils import FeedUpdater

logger = logging.getLogger('feedupdater')


class Command(BaseCommand):
    """Updates the users' feeds"""

    def handle(self, *args, **kwargs):
        if args:
            pk = args[0]
            feed = Feed.objects.get(pk=pk)
            feed.etag = ''
            return FeedUpdater(feed.url).update(use_etags=False)

        # Making a list of unique URLs. Makes one call whatever the number of
        # subscribers is.
        urls = Feed.objects.filter(muted=False).values_list('url', flat=True)
        unique_urls = {}
        map(unique_urls.__setitem__, urls, [])

        for url in unique_urls:
            try:
                try:
                    unique = UniqueFeed.objects.get(url=url)
                    if not unique.muted and unique.should_update():
                        enqueue(update_feed, url, timeout=20)
                except UniqueFeed.DoesNotExist:
                    enqueue(update_feed, url, timeout=20)
            except Exception:  # We don't know what to expect, and anyway
                               # we're reporting the exception
                if settings.DEBUG or not hasattr(settings, 'SENTRY_DSN'):
                    raise
                else:
                    client = Client(dsn=settings.SENTRY_DSN)
                    client.captureException()
        connection.close()
