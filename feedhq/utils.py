# -*- coding: utf-8 -*-
from django.conf import settings
from django.core.validators import EmailValidator, ValidationError

import redis

from redis_cache.cache import pool


def get_redis_connection(alias='default'):
    """
    Helper used for obtain a raw redis client.
    """
    connection_pool = pool.get_connection_pool(
        parser_class=redis.connection.HiredisParser,
        **settings.REDIS)
    return redis.Redis(connection_pool=connection_pool, **settings.REDIS)


def is_email(value):
    try:
        EmailValidator()(value)
    except ValidationError:
        return False
    else:
        return True
