import logging
import os

from django.conf import settings
from django.utils import timezone
from raven import Client

from ....tasks import enqueue
from ...models import UniqueFeed
from ...tasks import update_feed
from . import SentryCommand

logger = logging.getLogger('feedupdater')


TO_UPDATE = """
    SELECT
        id, url, modified, etag, backoff_factor, muted_reason, link, title,
        hub, subscribers, backoff_factor * {timeout_base} as tm
    FROM feeds_uniquefeed
    WHERE
        muted='false' AND
        (last_update + {update_period} * interval '1 minute' *
            backoff_factor^{backoff_exponent} < current_timestamp)
    ORDER BY last_loop ASC
    LIMIT %s
""".format(
    timeout_base=UniqueFeed.TIMEOUT_BASE,
    update_period=UniqueFeed.UPDATE_PERIOD,
    backoff_exponent=UniqueFeed.BACKOFF_EXPONENT,
)


class Command(SentryCommand):
    """Updates the users' feeds"""

    def handle_sentry(self, *args, **kwargs):
        if args:
            pk = args[0]
            feed = UniqueFeed.objects.get(pk=pk)
            feed.last_loop = timezone.now()
            feed.save(update_fields=['last_loop'])
            return update_feed(
                feed.url, etag=feed.etag, last_modified=feed.modified,
                subscribers=feed.subscribers,
                request_timeout=feed.request_timeout,
                backoff_factor=feed.backoff_factor, error=feed.error,
                link=feed.link, title=feed.title, hub=feed.hub,
            )

        ratio = UniqueFeed.UPDATE_PERIOD // 5

        uniques = UniqueFeed.objects.raw(
            TO_UPDATE,
            [max(1, UniqueFeed.objects.filter(muted=False).count() // ratio)])
        queued = set()

        try:
            for unique in uniques:
                enqueue(update_feed, args=[unique.url], kwargs={
                    'etag': unique.etag,
                    'last_modified': unique.modified,
                    'subscribers': unique.subscribers,
                    'request_timeout': unique.backoff_factor * 10,
                    'backoff_factor': unique.backoff_factor,
                    'error': unique.error,
                    'link': unique.link,
                    'title': unique.title,
                    'hub': unique.hub,
                }, timeout=unique.tm)
                queued.add(unique.pk)
        except Exception:  # We don't know what to expect, and anyway
                           # we're reporting the exception
            if settings.DEBUG or not 'SENTRY_DSN' in os.environ:
                raise
            else:
                client = Client(dsn=settings.SENTRY_DSN)
                client.captureException()
        finally:
            if queued:
                UniqueFeed.objects.filter(pk__in=list(queued)).update(
                    last_loop=timezone.now())
