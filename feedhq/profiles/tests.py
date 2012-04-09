import json

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase

from httplib2 import Response
from mock import patch


class ProfilesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test', 'test@example.com',
                                             'pass')
        self.client.login(username=self.user.username, password='pass')

    def test_profile(self):
        url = reverse('profile')
        response = self.client.get(url)
        self.assertContains(response, 'Stats')
        self.assertContains(response, '0 feeds')

    def test_change_password(self):
        url = reverse('profile')
        response = self.client.get(url)
        self.assertContains(response, 'Change your password')

        data = {
            'action': 'password',
            'current_password': 'lol',
            'new_password': 'foo',
            'new_password2': 'bar',
        }
        response = self.client.post(url, data)
        self.assertFormError(response, 'password_form', 'current_password',
                             'Incorrect password')
        self.assertFormError(response, 'password_form', 'new_password2',
                             "The two passwords didn't match")

        data['current_password'] = 'pass'
        data['new_password2'] = 'foo'

        response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, 'Your password was changed')

    def test_change_profile(self):
        url = reverse('profile')
        response = self.client.get(url)
        self.assertContains(response, 'Edit your profile')
        self.assertContains(response,
                            '<option value="UTC" selected="selected">')
        data = {
            'action': 'profile',
            'timezone': 'Foo/Bar',
            'entries_per_page': 25,
        }
        response = self.client.post(url, data)
        self.assertFormError(
            response, 'profile_form', 'timezone', (
                'Select a valid choice. Foo/Bar is not one of the '
                'available choices.'),
        )

        data['timezone'] = 'Europe/Paris'
        response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertEqual(User.objects.get().timezone, 'Europe/Paris')

        data['entries_per_page'] = 12
        response = self.client.post(url, data)
        self.assertFormError(
            response, 'profile_form', 'entries_per_page', (
                'Select a valid choice. 12 is not one of the '
                'available choices.'),
        )
        data['entries_per_page'] = 50
        response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertEqual(User.objects.get().entries_per_page, 50)

    def test_opml_export(self):
        url = reverse('export')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('attachment' in response['Content-Disposition'])
        self.assertEqual(len(response.content), 126)  # No feed yet

        cat = self.user.categories.create(name='Test', slug='test')
        cat.feeds.create(name='Test Feed',
                         url='http://example.com/test.atom')
        response = self.client.get(url)
        self.assertContains(response, 'xmlUrl="http://example.com/test.atom"')

    def test_read_later(self):
        url = reverse('profile')
        response = self.client.get(url)

        self.assertContains(
            response,
            'Your current read-it-later service is: <strong>None</strong>'
        )

    @patch("requests.get")
    def test_valid_readitlater_credentials(self, get):
        url = reverse('services', args=['readitlater'])
        response = self.client.get(url)
        self.assertContains(response, 'Read It Later')

        data = {
            'username': 'example',
            'password': 'samplepassword',
        }

        get.return_value.status_code = 200
        response = self.client.post(url, data, follow=True)
        get.assert_called_with(
            'https://readitlaterlist.com/v2/auth',
            params={'username': u'example',
                    'apikey': 'test read it later API key',
                    'password': u'samplepassword'},
        )

        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, ' as your reading list service')
        self.assertContains(response, ('Your current read-it-later service '
                                       'is: <strong>Read it later</strong>'))

        user = User.objects.get()
        self.assertEqual(user.read_later, 'readitlater')
        self.assertTrue(len(user.read_later_credentials) > 20)

    @patch("requests.get")
    def test_invalid_readitlater_credentials(self, get):
        url = reverse("services", args=['readitlater'])

        data = {
            'username': 'example',
            'password': 'wrong password',
        }

        get.return_value.status_code = 401
        response = self.client.post(url, data)
        self.assertContains(
            response,
            'Unable to verify your readitlaterlist credentials',
        )

    @patch("oauth2.Client")
    def test_valid_oauth_credentials(self, Client):
        client = Client.return_value

        client.request.return_value = [
            Response({}),
            "oauth_token=aabbccdd&oauth_token_secret=efgh1234"
        ]

        url = reverse("services", args=['readability'])
        data = {
            'username': 'example',
            'password': 'correct password',
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(
            response,
            "You have successfully added Readability",
        )

        client.request.assert_called_with(
            "https://www.readability.com/api/rest/v1/oauth/access_token/",
            method='POST',
            body=('x_auth_mode=client_auth&x_auth_password=correct+password&'
                  'x_auth_username=example'),
        )

        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(user.read_later, 'readability')
        self.assertEqual(json.loads(user.read_later_credentials), {
            "oauth_token": "aabbccdd",
            "oauth_token_secret": "efgh1234",
        })

    @patch("oauth2.Client")
    def test_invalid_oauth_credentials(self, Client):
        client = Client.return_value
        client.request.return_value = [Response({'status': 401}),
                                       "xAuth error"]

        url = reverse("services", args=['instapaper'])
        data = {
            'username': 'example',
            'password': 'incorrect password',
        }
        response = self.client.post(url, data)
        self.assertContains(response, "Unable to verify")
        client.request.assert_called_with(
            'https://www.instapaper.com/api/1/oauth/access_token',
            body=('x_auth_mode=client_auth&'
                  'x_auth_password=incorrect+password&'
                  'x_auth_username=example'),
            method='POST',
        )

    def test_disable_read_later(self):
        """Removing read later credentials"""
        self.user.read_later = 'readability'
        self.user.read_later_credentials = '{"foo":"bar","baz":"bah"}'
        self.user.save()

        response = self.client.get(reverse('profile'))
        url = reverse('services', args=['none'])
        self.assertContains(response, url)

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url, {}, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, "disabled reading list integration")
        self.assertNotContains(response, url)

        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(user.read_later, '')
        self.assertEqual(user.read_later_credentials, '')
