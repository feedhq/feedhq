from django.core.cache import cache
from rest_framework.authentication import (BaseAuthentication,
                                           get_authorization_header)

from ..profiles.models import User
from .exceptions import PermissionDenied
from .models import check_auth_token


class GoogleLoginAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'GoogleLogin'

    def authenticate(self, request):
        """GoogleLogin auth=<token>"""
        auth = get_authorization_header(request).decode('utf-8').split()

        if not auth or auth[0].lower() != 'googlelogin':
            raise PermissionDenied()

        if len(auth) == 1:
            raise PermissionDenied()

        if not auth[1].startswith('auth='):
            raise PermissionDenied()

        token = auth[1].split('auth=', 1)[1]
        return self.authenticate_credentials(token)

    def authenticate_credentials(self, token):
        user_id = check_auth_token(token)
        if user_id is False:
            raise PermissionDenied()
        cache_key = 'reader_user:{0}'.format(user_id)
        user = cache.get(cache_key)
        if user is None:
            try:
                user = User.objects.get(pk=user_id, is_active=True)
            except User.DoesNotExist:
                raise PermissionDenied()
            cache.set(cache_key, user, 5*60)
        return user, token
