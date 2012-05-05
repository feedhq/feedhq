from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand

from raven import Client

from ...models import Feed, Favicon


class Command(BaseCommand):
    """Fetches favicon updates and saves them if there are any"""
    option_list = BaseCommand.option_list + (
        make_option(
            '--all',
            action='store_true',
            dest='all',
            default=False,
            help='Force update of all existing favicons',
        ),
    )

    def handle(self, *args, **kwargs):
        links = Feed.objects.values_list('link', flat=True).distinct()
        for link in links:
            try:
                Favicon.objects.update_favicon(link,
                                               force_update=kwargs['all'])
            except Exception:
                if settings.DEBUG or not hasattr(settings, 'SENTRY_DSN'):
                    raise
                else:
                    client = Client(dsn=settings.SENTRY_DSN)
                    client.captureException()
