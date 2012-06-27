from django.conf import settings
from django.db import connection

from ..tasks import raven
from .utils import FeedUpdater


@raven
def update_feed(feed_url, use_etags=True):
    FeedUpdater(feed_url).update(use_etags)
    close_connection()


@raven
def read_later(entry_pk):
    from .models import Entry  # circular imports
    Entry.objects.get(pk=entry_pk).read_later()
    close_connection()


def close_connection():
    """Close the connection only if not in eager mode"""
    if not settings.RQ.get('eager', True):
        connection.close()
