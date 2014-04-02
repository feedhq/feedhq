# -*- coding: utf-8 -*-
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _


POST_TOKEN_DURATION = 60 * 30  # 30 minutes
AUTH_TOKEN_TIMEOUT = 3600 * 24 * 7  # 1 week

AUTH_TOKEN_LENGTH = 267
POST_TOKEN_LENGTH = 57


def check_auth_token(token):
    key = 'reader_auth_token:{0}'.format(token)
    value = cache.get(key)
    if value is None:
        try:
            token = AuthToken.objects.get(token=token)
        except AuthToken.DoesNotExist:
            return False
        value = token.user_id
        cache.set(key, value, AUTH_TOKEN_TIMEOUT)
    return int(value)


def check_post_token(token):
    key = 'reader_post_token:{0}'.format(token)
    value = cache.get(key)
    if value is None:
        return False
    return int(value)


def generate_auth_token(user, client='', user_agent=''):
    token = user.auth_tokens.create(client=client, user_agent=user_agent)
    key = 'reader_auth_token:{0}'.format(token.token)
    cache.set(key, user.pk, AUTH_TOKEN_TIMEOUT)
    return token.token


def generate_post_token(user):
    token = get_random_string(POST_TOKEN_LENGTH)
    key = 'reader_post_token:{0}'.format(token)
    cache.set(key, user.pk, POST_TOKEN_DURATION)
    return token


@python_2_unicode_compatible
class AuthToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('User'),
                             related_name='auth_tokens')
    token = models.CharField(
        _('Token'), max_length=300, db_index=True, unique=True,
        default=lambda: get_random_string(AUTH_TOKEN_LENGTH))
    date_created = models.DateTimeField(_('Creation date'),
                                        default=timezone.now)
    client = models.CharField(_('Client'), max_length=1023, blank=True)
    user_agent = models.TextField(_('User-Agent'), blank=True)

    def __str__(self):
        return u'Token for {0}'.format(self.user)

    class Meta:
        ordering = ('-date_created',)

    def delete(self):
        super(AuthToken, self).delete()
        cache.delete(self.cache_key)

    @property
    def cache_key(self):
        return 'reader_auth_token:{0}'.format(self.token)

    @property
    def user_pk(self):
        return self.user_id

    @property
    def cache_value(self):
        return cache.get(self.cache_key)

    @property
    def preview(self):
        return u'{0}…'.format(self.token[:8])
