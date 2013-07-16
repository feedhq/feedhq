# -*- coding: utf-8 -*-
import datetime

from django.utils import timezone

from .. import __version__


USER_AGENT = (
    'FeedHQ/%s (https://github.com/feedhq/feedhq; %%s; https://github.com/'
    'feedhq/feedhq/wiki/fetcher; like FeedFetcher-Google)'
) % __version__
FAVICON_FETCHER = USER_AGENT % 'favicon fetcher'


def is_feed(parsed):
    return hasattr(parsed.feed, 'title')


def epoch_to_utc(value):
    """Converts epoch (in seconds) values to a timezone-aware datetime."""
    return timezone.make_aware(
        datetime.datetime.fromtimestamp(value), timezone.utc)
