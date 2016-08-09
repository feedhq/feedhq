from datetime import timedelta

from django.utils import timezone

from ...models import AUTH_TOKEN_DAYS, AuthToken
from ....feeds.management.commands import SentryCommand


class Command(SentryCommand):
    """Updates the users' feeds"""

    def handle_sentry(self, *args, **kwargs):
        threshold = timezone.now() - timedelta(days=AUTH_TOKEN_DAYS)
        AuthToken.objects.filter(date_created__lte=threshold).delete()
