from .utils import FeedUpdater


def update_feed(feed_url, use_etags=True):
    FeedUpdater(feed_url).update(use_etags)


def read_later(entry_pk):
    from .models import Entry  # circular imports
    Entry.objects.get(pk=entry_pk).read_later()
