from functools import wraps

from django.contrib.auth import REDIRECT_FIELD_NAME

from ratelimitbackend.views import login

from .profiles.forms import AuthForm


def login_required(view_callable):
    def check_login(request, *args, **kwargs):
        if (request.user.is_authenticated() or
            ('HTTP_ACCEPT' in request.META and
             'text/html' not in request.META['HTTP_ACCEPT'] and
             '*/*' not in request.META['HTTP_ACCEPT'])):
            return view_callable(request, *args, **kwargs)

        assert hasattr(request, 'session'), "Session middleware needed."
        login_kwargs = {
            'extra_context': {
                REDIRECT_FIELD_NAME: request.get_full_path(),
                'from_decorator': True,
            },
            'authentication_form': AuthForm,
        }
        return login(request, **login_kwargs)
    return wraps(view_callable)(check_login)
