from optparse import make_option

from ...models import UniqueFeed, enqueue_favicon
from . import SentryCommand


class Command(SentryCommand):
    """Fetches favicon updates and saves them if there are any"""
    option_list = SentryCommand.option_list + (
        make_option(
            '--all',
            action='store_true',
            dest='all',
            default=False,
            help='Force update of all existing favicons',
        ),
    )

    def handle_sentry(self, *args, **kwargs):
        urls = UniqueFeed.objects.filter(muted=False).values_list(
            'url', flat=True).distinct()
        for url in urls:
            enqueue_favicon(url, force_update=kwargs['all'])
