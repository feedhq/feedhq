import os

from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand
from raven import Client

from ...models import Feed, UniqueFeed, enqueue_favicon


class Command(BaseCommand):
    """Updates the users' feeds"""

    def handle(self, *args, **kwargs):
        try:
            missing = Feed.objects.raw(
                """
                select id, url from feeds_feed f where not exists (
                    select 1 from feeds_uniquefeed u where f.url = u.url
                )
                """)
            uniques = []
            urls = Counter([f.url for f in missing])
            for url in urls:
                uniques.append(UniqueFeed(url=url, subscribers=urls[url]))
            UniqueFeed.objects.bulk_create(uniques)

            if not settings.TESTS:
                missing_favicons = UniqueFeed.objects.raw(
                    """
                    select id, link from feeds_uniquefeed u
                    where
                        u.link != '' and
                        not exists (
                            select 1 from feeds_favicon f
                            where f.url = u.link
                        )
                    """)
                for feed in missing_favicons:
                    enqueue_favicon(feed.link)
        except Exception:
            if settings.DEBUG or not 'SENTRY_DSN' in os.environ:
                raise
            client = Client()
            client.captureException()
