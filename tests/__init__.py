import os

from io import BytesIO as BaseBytesIO

from django.conf import settings
from django.test import TestCase as BaseTestCase
from django_webtest import WebTest as BaseWebTest
from rache import job_key
from requests import Response

from feedhq import es
from feedhq.utils import get_redis_connection


TEST_DATA = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')


class BytesIO(BaseBytesIO):
    def read(self, *args, **kwargs):
        kwargs.pop('decode_content', None)
        return super(BytesIO, self).read(*args, **kwargs)


def data_file(name):
    return os.path.join(TEST_DATA, name)


def responses(code, path=None, redirection=None, data=None,
              headers={'Content-Type': 'text/xml'}):
    response = Response()
    response.status_code = code
    if path is not None:
        with open(data_file(path), 'rb') as f:
            response.raw = BytesIO(f.read())
    elif data is not None:
        response._content = data.encode('utf-8')
    if redirection is not None:
        temp = Response()
        temp.status_code = 301 if 'permanent' in redirection else 302
        temp.url = path
        response.history.append(temp)
        response.url = redirection
    response.headers = headers
    return response


class ESTests(object):
    @classmethod
    def tearDownClass(cls):  # noqa
        super(ESTests, cls).tearDownClass()
        delete_es_indices()

    @classmethod
    def setUpClass(cls):  # noqa
        super(ESTests, cls).setUpClass()
        delete_es_indices()


class TestCase(ESTests, BaseTestCase):
    def tearDown(self):  # noqa
        """Clean up the rache:* redis keys"""
        get_redis_connection().flushdb()
    setUp = tearDown


class WebTest(ESTests, BaseWebTest):
    pass


def delete_es_indices():
    indices = es.client.indices.status('')['indices'].keys()
    for index in indices:
        if index.startswith(settings.ES_INDEX_PREFIX):
            es.client.indices.delete(index)
    es.wait_for_yellow()


def patch_job(name, **kwargs):
    redis = get_redis_connection()
    for key, value in list(kwargs.items()):
        if value is None:
            redis.hdel(job_key(name), key)
            kwargs.pop(key)
    redis.hmset(job_key(name), kwargs)
