# -*- coding: utf-8 -*-
import datetime

from django.utils import timezone

from rache import job_key, job_details

from .. import __version__
from ..utils import get_redis_connection


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


class JobNotFound(Exception):
    pass


def get_job(name):
    redis = get_redis_connection()
    key = job_key(name)
    if not redis.exists(key):
        raise JobNotFound
    return job_details(name, connection=redis)
