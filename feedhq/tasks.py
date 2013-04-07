"""
Generic helpers for RQ task execution
"""
from __future__ import absolute_import

import redis
import rq

from django.conf import settings


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
