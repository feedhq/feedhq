# -*- coding: utf-8 -*-
import redis
from django.conf import settings
from django.core.validators import EmailValidator, ValidationError


def get_redis_connection():
    """
    Helper used for obtain a raw redis client.
    """
    from redis_cache.cache import pool
    client = redis.Redis(**settings.REDIS)
    client.connection_pool = pool.get_connection_pool(
        client,
        parser_class=redis.connection.HiredisParser,
        connection_pool_class=redis.ConnectionPool,
        connection_pool_class_kwargs={},
        **settings.REDIS)
    return client


def is_email(value):
    try:
        EmailValidator()(value)
    except ValidationError:
        return False
    else:
        return True
