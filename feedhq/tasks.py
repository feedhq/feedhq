"""
Generic helpers for RQ task execution
"""
from __future__ import absolute_import

import rq

from django.conf import settings

from .utils import get_redis_connection


def enqueue(function, args=None, kwargs=None, timeout=None, queue='default'):
    async = not settings.RQ_EAGER

    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    conn = get_redis_connection()
    queue = rq.Queue(queue, connection=conn, async=async)
    return queue.enqueue_call(func=function, args=tuple(args), kwargs=kwargs,
                              timeout=timeout)
