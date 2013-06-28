# -*- coding: utf-8 -*-
from .. import __version__


USER_AGENT = (
    'FeedHQ/%s (https://github.com/feedhq/feedhq; %%s; https://github.com/'
    'feedhq/feedhq/wiki/fetcher; like FeedFetcher-Google)'
) % __version__
FAVICON_FETCHER = USER_AGENT % 'favicon fetcher'


def is_feed(parsed):
    return not parsed.bozo and hasattr(parsed.feed, 'title')
