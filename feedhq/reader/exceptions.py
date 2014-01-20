from rest_framework import exceptions, status


class ReaderException(exceptions.APIException):
    pass


class PermissionDenied(ReaderException):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = 'Error=BadAuthentication'


class BadToken(ReaderException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = 'Invalid POST token'
