"""
Generic helpers for RQ task execution

Add to your settings:

    RQ = {
        'host': 'localhost',
        'port': 6379,
        'password': None,
        'db': 0,
        'charset': 'utf-8',
        'errors': 'strict',
        'unix_socket_path': None
        'eager': False,
    }

Everything's optional, these are just the default values.
"""
from __future__ import absolute_import
from functools import wraps

import redis
import rq

from django.conf import settings
from raven import Client
from rq.timeouts import JobTimeoutException


def enqueue(function, args=None, kwargs=None, timeout=None, queue='default'):
    opts = getattr(settings, 'RQ', {})
    eager = opts.get('eager', False)
    async = not eager

    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    if 'eager' in opts:
        opts = opts.copy()
        opts.pop('eager')

    conn = redis.Redis(**opts)
    queue = rq.Queue(queue, connection=conn, async=async)
    return queue.enqueue_call(func=function, args=tuple(args), kwargs=kwargs,
                              timeout=timeout)


def raven(function):
    @wraps(function)
    def ravenify(*args, **kwargs):
        try:
            function(*args, **kwargs)
        except Exception as e:
            if not settings.DEBUG and hasattr(settings, 'SENTRY_DSN'):
                if not isinstance(e, JobTimeoutException):
                    client = Client(dsn=settings.SENTRY_DSN)
                    client.captureException()
            raise
    return ravenify
