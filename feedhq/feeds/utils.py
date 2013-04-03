# -*- coding: utf-8 -*-
from .. import __version__


USER_AGENT = (
    'FeedHQ/%s (https://github.com/feedhq/feedhq; %%s; https://github.com/'
    'feedhq/feedhq/wiki/User-Agent)'
) % __version__
FAVICON_FETCHER = USER_AGENT % 'favicon fetcher'
