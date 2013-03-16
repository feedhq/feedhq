import os

from django.test import TestCase

from feedhq.settings import parse_redis_url, parse_email_url


class SettingsTests(TestCase):
    def test_redis_url(self):
        os.environ['REDIS_URL'] = 'redis://password@domain:12/44'
        self.assertEqual(parse_redis_url(), ({
            'host': 'domain',
            'port': 12,
            'password': 'password',
            'db': 44,
        }, False))

        os.environ['REDIS_URL'] = 'redis://domain:6379/44?eager=True'
        self.assertEqual(parse_redis_url(), ({
            'host': 'domain',
            'port': 6379,
            'password': None,
            'db': 44,
        }, True))

        os.environ['REDIS_URL'] = (
            'redis://domain:6379/44?eager=True&foo=bar&port=stuff'
        )
        self.assertEqual(parse_redis_url(), ({
            'host': 'domain',
            'port': 6379,
            'password': None,
            'db': 44,
        }, True))

    def test_email_url(self):
        os.environ['EMAIL_URL'] = (
            'smtp://bruno:test1234@example.com:587'
            '?use_tls=True&backend=custom.backend.EmailBackend'
        )
        self.assertEqual(parse_email_url(), {
            'BACKEND': 'custom.backend.EmailBackend',
            'HOST': 'example.com',
            'PORT': 587,
            'USE_TLS': True,
            'USER': 'bruno',
            'PASSWORD': 'test1234',
            'SUBJECT_PREFIX': '[FeedHQ] ',
        })
