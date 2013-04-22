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
        links = UniqueFeed.objects.values_list('link', flat=True).distinct()
        for link in links:
            enqueue_favicon(link, force_update=kwargs['all'])
