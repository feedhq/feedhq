import warnings

from django.test import TestCase
from django.test.client import Client as BaseClient


class Client(BaseClient):
    def login(self, *args, **kwargs):
        with warnings.catch_warnings(record=True) as w:
            ret = super(Client, self).login(*args, **kwargs)
            assert len(w) == 1
        return ret


class FeedHQTestCase(TestCase):
    client_class = Client
