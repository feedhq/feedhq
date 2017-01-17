import os
from io import BytesIO as BaseBytesIO
from uuid import uuid4

from django.test import TestCase as BaseTestCase
from django_webtest import WebTest as BaseWebTest
from feedhq import es
from feedhq.utils import get_redis_connection
from rache import job_key
from requests import Response


TEST_DATA = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')


class BytesIO(BaseBytesIO):
    def read(self, *args, **kwargs):
        kwargs.pop('decode_content', None)
        return super(BytesIO, self).read(*args, **kwargs)


def data_file(name):
    return os.path.join(TEST_DATA, name)


def responses(code, path=None, redirection=None, data=None,
              url=None,
              headers={'Content-Type': 'text/xml'}):
    response = Response()
    response.status_code = code
    if path is not None and redirection is None:
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
        headers['location'] = path
    if url is None:
        if redirection is not None:
            url = redirection
        else:
            url = 'https://example.com/{}'.format(str(uuid4()))
    response.url = url
    response.headers = headers
    return response


def resolve_url(url, *args, **kwargs):
    response = Response()
    response.status_code = 200
    response.url = url
    return response


class ESTests(object):
    def counts(self, user, **kwargs):
        es_entries = es.manager.user(user)
        for name, filters in kwargs.items():
            es_entries = es_entries.query_aggregate(name, **filters)
        results = es_entries.fetch(per_page=0)['aggregations']['entries']
        return {name: results[name]['doc_count'] for name in kwargs}


class TestCase(ESTests, BaseTestCase):
    def tearDown(self):  # noqa
        """Clean up the rache:* redis keys"""
        get_redis_connection().flushdb()
    setUp = tearDown


class WebTest(ESTests, BaseWebTest):
    pass


def patch_job(name, **kwargs):
    redis = get_redis_connection()
    for key, value in list(kwargs.items()):
        if value is None:
            redis.hdel(job_key(name), key)
            kwargs.pop(key)
    redis.hmset(job_key(name), kwargs)
