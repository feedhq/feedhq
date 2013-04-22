import os

from django.conf import settings
from django.core.management.base import BaseCommand
from raven import Client


class SentryCommand(BaseCommand):
    def handle(self, *args, **kwargs):
        try:
            self.handle_sentry(*args, **kwargs)
        except Exception:
            if settings.DEBUG or not 'SENTRY_DSN' in os.environ:
                raise
            client = Client()
            client.captureException()
