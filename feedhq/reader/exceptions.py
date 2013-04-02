from rest_framework import exceptions, status


class ReaderException(exceptions.APIException):
    pass


class PermissionDenied(ReaderException):
    status_code = status.HTTP_403_FORBIDDEN
    detail = 'Error=BadAuthentication'


class BadToken(ReaderException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = 'Invalid POST token'
