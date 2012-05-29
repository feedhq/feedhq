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
    }

Everything's optional, these are just the default values.
"""
import redis
import rq

from django.conf import settings


def enqueue(function, *args, **kwargs):
    opts = getattr(settings, 'RQ', {})
    conn = redis.Redis(**opts)
    queue = rq.Queue('default', connection=conn)
    return queue.enqueue(function, *args, **kwargs)
