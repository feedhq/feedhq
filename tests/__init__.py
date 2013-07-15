import os

from io import BytesIO as BaseBytesIO

from django.test import TestCase
from rache import r
from requests import Response


TEST_DATA = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')


class BytesIO(BaseBytesIO):
    def read(self, *args, **kwargs):
        kwargs.pop('decode_content')
        return super(BytesIO, self).read(*args, **kwargs)


def test_file(name):
    return os.path.join(TEST_DATA, name)


def responses(code, path=None, redirection=None,
              headers={'Content-Type': 'text/xml'}):
    response = Response()
    response.status_code = code
    if path is not None:
        with open(test_file(path), 'r') as f:
            response.raw = BytesIO(f.read())
    if redirection is not None:
        temp = Response()
        temp.status_code = 301 if 'permanent' in redirection else 302
        temp.url = path
        response.history.append(temp)
        response.url = redirection
    response.headers = headers
    return response


class ClearRedisTestCase(TestCase):
    def tearDown(self):  # noqa
        """Clean up the rache:* redis keys"""
        r.flushall()
    setUp = tearDown
