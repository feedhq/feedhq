from . import SentryCommand
from ...models import enqueue_favicon, UniqueFeed


class Command(SentryCommand):
    """Fetches favicon updates and saves them if there are any"""

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true', dest='all',
                            default=False,
                            help='Force update of all existing favicons')

    def handle_sentry(self, *args, **kwargs):
        urls = UniqueFeed.objects.filter(muted=False).values_list(
            'url', flat=True).distinct()
        for url in urls:
            enqueue_favicon(url, force_update=kwargs['all'])
