from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.core.validators import email_re

from ratelimitbackend.backends import RateLimitMixin


class RateLimitMultiBackend(RateLimitMixin, ModelBackend):
    """A backend that allows login via username or email, rate-limited."""
    def authenticate(self, username=None, password=None, request=None):
        if email_re.search(username):
            try:
                username = User.objects.get(email=username).username
            except User.DoesNotExist:
                pass
        return super(RateLimitMultiBackend, self).authenticate(username,
                                                               password,
                                                               request)
