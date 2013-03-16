"""
Generic helpers for RQ task execution
"""
from __future__ import absolute_import
from functools import wraps

import os
import redis
import rq

from django.conf import settings
from raven import Client


def enqueue(function, args=None, kwargs=None, timeout=None, queue='default'):
    async = not settings.RQ_EAGER

    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    conn = redis.Redis(**settings.REDIS)
    queue = rq.Queue(queue, connection=conn, async=async)
    return queue.enqueue_call(func=function, args=tuple(args), kwargs=kwargs,
                              timeout=timeout)


def raven(function):
    @wraps(function)
    def ravenify(*args, **kwargs):
        try:
            function(*args, **kwargs)
        except Exception:
            if settings.DEBUG:
                raise

            if 'SENTRY_DSN' in os.environ:
                client = Client()
            elif hasattr(settings, 'SENTRY_DSN'):
                client = Client(dsn=settings.SENTRY_DSN)
            else:
                raise
            client.captureException()
            raise
    return ravenify
