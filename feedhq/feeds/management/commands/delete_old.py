from datetime import timedelta

from django.utils import timezone

from . import SentryCommand
from ....profiles.models import User


class Command(SentryCommand):
    def handle_sentry(self, **options):
        users = User.objects.filter(ttl__isnull=False)
        for user in users:
            limit = timezone.now() - timedelta(days=user.ttl)
            user.entries.filter(date__lte=limit).delete()
