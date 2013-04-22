from ...models import UniqueFeed
from . import SentryCommand


class Command(SentryCommand):
    """Updates the users' feeds"""

    def handle_sentry(self, *args, **kwargs):
        unsubscribed = UniqueFeed.objects.raw(
            """
            select id from feeds_uniquefeed u where not exists (
                select 1 from feeds_feed f where f.url = u.url
            )
            """)
        pks = [u.pk for u in unsubscribed]
        UniqueFeed.objects.filter(pk__in=pks).delete()
