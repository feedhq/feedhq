from collections import Counter

from django.conf import settings

from ...models import Feed, UniqueFeed, enqueue_favicon
from . import SentryCommand


class Command(SentryCommand):
    """Updates the users' feeds"""

    def handle_sentry(self, *args, **kwargs):
        missing = Feed.objects.raw(
            """
            select f.id, f.url
            from
                feeds_feed f
                left join auth_user u on f.user_id = u.id
            where
                not exists (
                    select 1 from feeds_uniquefeed u where f.url = u.url
                ) and
                u.is_suspended = false
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
