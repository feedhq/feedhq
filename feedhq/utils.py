from django.conf import settings
from django.middleware.csrf import (
    CsrfViewMiddleware, REASON_NO_CSRF_COOKIE, REASON_NO_REFERER,
    REASON_BAD_REFERER, REASON_BAD_TOKEN, _sanitize_token, _get_new_csrf_key,
)
from django.utils.crypto import constant_time_compare
from django.utils.http import same_origin

middleware = CsrfViewMiddleware()


def manual_csrf_check(request):
    """
    Performs a CSRF check for a specific request.

    Useful for in-view CSRF checks.

    Returns an HTTP response in case of CSRF failure.
    """
    try:
        csrf_token = _sanitize_token(
            request.COOKIES[settings.CSRF_COOKIE_NAME]
        )
        request.META['CSRF_COOKIE'] = csrf_token
    except KeyError:
        csrf_token = None
        request.META["CSRF_COOKIE"] = _get_new_csrf_key()

    if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
        if request.is_secure():
            referer = request.META.get('HTTP_REFERER')
            if referer is None:
                return middleware._reject(request, REASON_NO_REFERER)

            good_referer = 'https://%s/' % request.get_host()
            if not same_origin(referer, good_referer):
                reason = REASON_BAD_REFERER % (referer, good_referer)
                return middleware._reject(request, reason)

        if csrf_token is None:
            return middleware._reject(request, REASON_NO_CSRF_COOKIE)

        request_csrf_token = ""
        if request.method == "POST":
            request_csrf_token = request.POST.get('csrfmiddlewaretoken', '')

        if request_csrf_token == "":
            request_csrf_token = request.META.get('HTTP_X_CSRFTOKEN', '')

        if not constant_time_compare(request_csrf_token, csrf_token):
            return middleware._reject(request, REASON_BAD_TOKEN)
