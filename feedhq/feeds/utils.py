# -*- coding: utf-8 -*-
import datetime
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from rache import job_details, job_key

from .. import __version__
from ..utils import get_redis_connection


USER_AGENT = (
    'FeedHQ/%s (https://github.com/feedhq/feedhq; %%s; https://github.com/'
    'feedhq/feedhq/wiki/fetcher; like FeedFetcher-Google)'
) % __version__
FAVICON_FETCHER = USER_AGENT % 'favicon fetcher'
LINK_CHECKER = USER_AGENT % 'ping'


def is_feed(parsed):
    return hasattr(parsed.feed, 'title')


def epoch_to_utc(value):
    """Converts epoch (in seconds) values to a timezone-aware datetime."""
    return timezone.make_aware(
        datetime.datetime.fromtimestamp(value), timezone.utc)


class JobNotFound(Exception):
    pass


def get_job(name):
    redis = get_redis_connection()
    key = job_key(name)
    if not redis.exists(key):
        raise JobNotFound
    return job_details(name, connection=redis)


def remove_utm_tags(guid):
    parts = list(urlsplit(guid))
    qs = parse_qs(parts[3])  # [3] is query component
    filtered = sorted([(k, v) for k, v in qs.items()
                       if not k.startswith('utm_')])
    parts[3] = urlencode(filtered, doseq=True)
    return urlunsplit(parts)


def resolve_url(url):
    if settings.TESTS:
        if str(type(requests.head)) != "<class 'unittest.mock.MagicMock'>":
            raise ValueError("Not mocked")
    cache_key = 'resolve_url:{0}'.format(url)
    resolved = cache.get(cache_key)
    if resolved is None:
        resolved = url
        response = requests.head(url, headers={'User-Agent': LINK_CHECKER},
                                 allow_redirects=True)
        if response.status_code == 200:
            resolved = response.url
        cache.set(cache_key, resolved, 3600 * 24 * 5)
    return resolved
