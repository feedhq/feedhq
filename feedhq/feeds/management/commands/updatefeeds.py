import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from raven import Client

from ....tasks import enqueue
from ...models import UniqueFeed
from ...tasks import update_feed

logger = logging.getLogger('feedupdater')


TO_UPDATE = """
    SELECT id, url, backoff_factor * {timeout_base} as tm
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


class Command(BaseCommand):
    """Updates the users' feeds"""

    def handle(self, *args, **kwargs):
        if args:
            pk = args[0]
            feed = UniqueFeed.objects.get(pk=pk)
            return update_feed(feed.url, use_etags=False)

        uniques = UniqueFeed.objects.raw(
            TO_UPDATE,
            [max(1, UniqueFeed.objects.filter(muted=False).count() // 9)])
        queued = set()

        try:
            for unique in uniques:
                enqueue(update_feed, args=[unique.url],
                        timeout=unique.tm)
                queued.add(unique.pk)
        except Exception:  # We don't know what to expect, and anyway
                           # we're reporting the exception
            if settings.DEBUG or not hasattr(settings, 'SENTRY_DSN'):
                raise
            else:
                client = Client(dsn=settings.SENTRY_DSN)
                client.captureException()
        finally:
            if queued:
                UniqueFeed.objects.filter(pk__in=list(queued)).update(
                    last_loop=timezone.now())
