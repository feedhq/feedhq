from . import SentryCommand
from ....profiles.models import User


class Command(SentryCommand):
    def handle_sentry(self, **options):
        users = User.objects.all()
        for user in users:
            user.delete_old()
