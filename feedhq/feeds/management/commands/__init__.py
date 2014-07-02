import os

from django.conf import settings
from django.core.management.base import BaseCommand
from raven import Client


class SentryCommand(BaseCommand):
    ignore_exceptions = None

    def handle(self, *args, **kwargs):
        try:
            self.handle_sentry(*args, **kwargs)
        except Exception as e:
            if (
                self.ignore_exceptions is not None and
                isinstance(e, self.ignore_exceptions)
            ) or settings.DEBUG or 'SENTRY_DSN' not in os.environ:
                raise
            client = Client()
            client.captureException()
