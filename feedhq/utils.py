# -*- coding: utf-8 -*-
from django.core.cache import get_cache
from django.core.validators import EmailValidator, ValidationError


def get_redis_connection(alias='default'):
    """
    Helper used for obtain a raw redis client.
    """
    cache = get_cache(alias)
    return cache._client


def is_email(value):
    try:
        EmailValidator()(value)
    except ValidationError:
        return False
    else:
        return True
