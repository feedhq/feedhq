import sys

from django.core.management.base import BaseCommand

from ...models import Feed
from ...utils import FeedUpdater


class Command(BaseCommand):
    """Updates the user's feeds"""

    def handle(self, *args, **kwargs):
        if args:
            pk = args[0]
            feed = Feed.objects.get(pk=pk)
            feed.etag = ''
            return FeedUpdater(feed.url).update()

        # Making a list of unique URLs. Makes one call whatever the number of
        # subscribers is.
        urls = Feed.objects.filter(muted=False).values_list('url', flat=True)
        unique_urls = {}
        map(unique_urls.__setitem__, urls, [])
        urls = unique_urls.keys()

        for url in urls:
            subscriber_count = Feed.objects.filter(url=url,
                                                   muted=False).count()

            plural = ''
            if subscriber_count > 1:
                plural = 's'

            agent_detail = ' (%s subscriber%s)' % (subscriber_count, plural)
            try:
                updater = FeedUpdater(url, agent=agent_detail)
                updater.update()
            except Exception:  # We don't know what to expect, and anyway
                               # we're reporting the exception
                from django.conf import settings
                if settings.DEBUG:
                    raise
                else:
                    self.handle_exception(sys.exc_info(), url)

    def handle_exception(self, exc_info, url):
        from django.core.mail import mail_admins
        import traceback

        # Building a human-readable traceback
        traceback_str = 'Feed was: %s\n\n' % url
        traceback_str += '\n'.join(traceback.format_exception(*(exc_info)))

        subject = 'Error updating feeds'
        mail_admins(subject, traceback_str, fail_silently=True)
