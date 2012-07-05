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


def enqueue(function, *args, **kwargs):
    opts = getattr(settings, 'RQ', {})
    eager = opts.get('eager', False)
    queue_name = kwargs.pop('queue', 'default')
    if eager:
        kwargs.pop('timeout', None)  # timeout is for RQ only
        return function(*args, **kwargs)

    else:
        conn = redis.Redis(**opts)
        queue = rq.Queue(queue_name, connection=conn)
        return queue.enqueue(function, *args, **kwargs)


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
