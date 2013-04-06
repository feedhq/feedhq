from optparse import make_option

from django.core.management.base import BaseCommand

from ...models import UniqueFeed, enqueue_favicon


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
        links = UniqueFeed.objects.values_list('link', flat=True).distinct()
        for link in links:
            enqueue_favicon(link, force_update=kwargs['all'])
