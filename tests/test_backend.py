import warnings

from django.contrib.auth import authenticate

from . import TestCase
from .factories import UserFactory


class BackendTest(TestCase):
    def test_case_insensitive_username(self):
        user = UserFactory.create(username='TeSt')

        with warnings.catch_warnings(record=True) as w:
            self.assertEqual(authenticate(username='TeSt', password='test').pk,
                             user.pk)

            self.assertEqual(authenticate(username='test', password='test').pk,
                             user.pk)

            self.assertEqual(authenticate(username=user.email.lower(),
                                          password='test').pk, user.pk)

            self.assertEqual(authenticate(username=user.email.upper(),
                                          password='test').pk, user.pk)
            self.assertEqual(len(w), 4)
