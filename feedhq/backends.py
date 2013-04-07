from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.core.validators import email_re

from ratelimitbackend.backends import RateLimitMixin


class CaseInsensitiveModelBackend(ModelBackend):
    def authenticate(self, username, password):
        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            return None
        else:
            if user.check_password(password):
                return user


class RateLimitMultiBackend(RateLimitMixin, CaseInsensitiveModelBackend):
    """A backend that allows login via username or email, rate-limited."""
    def authenticate(self, username=None, password=None, request=None):
        if email_re.search(username):
            try:
                username = User.objects.get(email__iexact=username).username
            except User.DoesNotExist:
                pass
        return super(RateLimitMultiBackend, self).authenticate(username,
                                                               password,
                                                               request)
