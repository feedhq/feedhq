import feedparser
import json

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

from django_webtest import WebTest
from httplib2 import Response as _Response
from mock import patch

from feedhq.feeds.utils import USER_AGENT

from . import responses


class ProfilesTest(WebTest):
    def setUp(self):  # noqa
        self.user = User.objects.create_user('test', 'test@example.com',
                                             'pass')

    def test_profile(self):
        url = reverse('stats')
        response = self.app.get(url, user='test')
        self.assertContains(response, 'Stats')
        self.assertContains(response, '0 feeds')

    def test_change_password(self):
        url = reverse('password')
        response = self.app.get(url, user='test')
        self.assertContains(response, 'Change your password')

        form = response.forms['password']

        data = {
            'current_password': 'lol',
            'new_password': 'foo',
            'new_password2': 'bar',
        }
        for key, value in data.items():
            form[key] = value
        response = form.submit()
        self.assertFormError(response, 'form', 'current_password',
                             'Incorrect password')
        self.assertFormError(response, 'form', 'new_password2',
                             "The two passwords didn't match")

        form['current_password'] = 'pass'
        form['new_password2'] = 'foo'

        response = form.submit().follow()
        self.assertContains(response, 'Your password was changed')

    def test_change_profile(self):
        url = reverse('profile')
        response = self.app.get(url, user='test')
        self.assertContains(response, 'Edit your profile')
        self.assertContains(response,
                            '<option value="UTC" selected="selected">')
        form = response.forms['profile']
        data = {
            'username': 'test',
            'entries_per_page': 25,
        }
        for key, value in data.items():
            form[key] = value
        form['timezone'].force_value('Foo/Bar')
        response = form.submit()
        self.assertFormError(
            response, 'form', 'timezone', (
                'Select a valid choice. Foo/Bar is not one of the '
                'available choices.'),
        )

        form['timezone'] = 'Europe/Paris'
        response = form.submit().follow()
        self.assertEqual(User.objects.get().timezone, 'Europe/Paris')

        form['entries_per_page'].force_value(12)
        response = form.submit()
        self.assertFormError(
            response, 'form', 'entries_per_page', (
                'Select a valid choice. 12 is not one of the '
                'available choices.'),
        )
        form['entries_per_page'] = 50
        response = form.submit().follow()
        self.assertEqual(User.objects.get().entries_per_page, 50)

        # changing a username
        new = User.objects.create_user('foobar', 'foo@bar.com', 'pass')

        form['username'] = 'foobar'
        response = form.submit()
        self.assertFormError(response, 'form', 'username',
                             'This username is already taken.')

        new.username = 'lol'
        new.save()

        self.assertEqual(User.objects.get(pk=self.user.pk).username, 'test')
        response = form.submit()
        self.assertEqual(User.objects.get(pk=self.user.pk).username, 'foobar')

    @patch("requests.get")
    def test_opml_export(self, get):
        url = reverse('opml_export')
        response = self.app.get(url, user='test')
        self.assertEqual(response.status_code, 200)
        self.assertTrue('attachment' in response['Content-Disposition'])
        self.assertEqual(len(response.content), 126)  # No feed yet

        cat = self.user.categories.create(name='Test', slug='test')

        get.return_value = responses(304)
        cat.feeds.create(name='Test Feed',
                         url='http://example.com/test.atom')
        get.assert_called_with(
            'http://example.com/test.atom',
            headers={"User-Agent": USER_AGENT % '1 subscriber',
                     "Accept": feedparser.ACCEPT_HEADER}, timeout=10)
        response = self.app.get(url, user='test')
        self.assertContains(response, 'xmlUrl="http://example.com/test.atom"')

    def test_read_later(self):
        url = reverse('read_later')
        response = self.app.get(url, user='test')

        self.assertContains(
            response,
            "You don't have any read-it-later service configured yet."
        )

    def test_sharing(self):
        url = reverse('sharing')
        response = self.app.get(url, user='test')
        form = response.forms['sharing']
        form['sharing_twitter'] = True
        response = form.submit().follow()
        self.assertTrue(User.objects.get().sharing_twitter)

    @patch("requests.get")
    def test_valid_readitlater_credentials(self, get):
        url = reverse('services', args=['readitlater'])
        response = self.app.get(url, user='test')
        self.assertContains(response, 'Read It Later')

        form = response.forms['readitlater']
        form['username'] = 'example'
        form['password'] = 'samplepassword'

        get.return_value.status_code = 200
        response = form.submit().follow()
        get.assert_called_with(
            'https://readitlaterlist.com/v2/auth',
            params={'username': u'example',
                    'apikey': 'test read it later API key',
                    'password': u'samplepassword'},
        )

        self.assertContains(response, ' as your reading list service')
        self.assertContains(response, ('Your current read-it-later service '
                                       'is: <strong>Read it later</strong>'))

        user = User.objects.get()
        self.assertEqual(user.read_later, 'readitlater')
        self.assertTrue(len(user.read_later_credentials) > 20)

    @patch("requests.get")
    def test_invalid_readitlater_credentials(self, get):
        url = reverse("services", args=['readitlater'])
        response = self.app.get(url, user='test')
        form = response.forms['readitlater']

        form['username'] = 'example'
        form['password'] = 'wrong password'

        get.return_value.status_code = 401
        response = form.submit()
        self.assertContains(
            response,
            'Unable to verify your readitlaterlist credentials',
        )

    @patch("oauth2.Client")
    def test_valid_oauth_credentials(self, Client):  # noqa
        client = Client.return_value

        client.request.return_value = [
            _Response({}),
            "oauth_token=aabbccdd&oauth_token_secret=efgh1234"
        ]

        url = reverse("services", args=['readability'])
        response = self.app.get(url, user='test')
        form = response.forms['readability']
        form['username'] = 'example'
        form['password'] = 'correct password'
        response = form.submit().follow()
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
    def test_invalid_oauth_credentials(self, Client):  # noqa
        client = Client.return_value
        client.request.return_value = [_Response({'status': 401}),
                                       "xAuth error"]

        url = reverse("services", args=['instapaper'])
        response = self.app.get(url, user='test')
        form = response.forms['instapaper']
        data = {
            'username': 'example',
            'password': 'incorrect password',
        }
        for key, value in data.items():
            form[key] = value
        response = form.submit()
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

        response = self.app.get(reverse('read_later'), user='test')
        url = reverse('services', args=['none'])
        self.assertContains(response, url)

        response = self.app.get(url, user='test')
        self.assertEqual(response.status_code, 200)
        form = response.forms['disable']
        response = form.submit().follow()
        self.assertContains(response, "disabled reading list integration")
        self.assertNotContains(response, url)

        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(user.read_later, '')
        self.assertEqual(user.read_later_credentials, '')

    def test_delete_account(self):
        self.assertEqual(User.objects.count(), 1)
        url = reverse('destroy_account')
        response = self.app.get(url, user='test')
        self.assertContains(response, 'Delete your account')

        form = response.forms['delete']
        form['password'] = 'test'
        response = form.submit()
        self.assertContains(response, 'The password you entered was incorrect')

        form['password'] = 'pass'
        response = form.submit().follow()
        self.assertContains(response, "Good bye")

    def test_login_via_username_or_email(self):
        url = reverse('login')

        response = self.app.get(url)
        self.assertContains(response, 'Username or Email')
        form = response.forms['login']

        form['username'] = 'test'
        form['password'] = 'pass'
        response = form.submit()
        self.assertRedirects(response, '/')

        self.renew_app()
        response = self.app.get(url)
        form = response.forms['login']

        form['username'] = 'test@example.com'
        form['password'] = 'pass'
        response = form.submit()
        self.assertRedirects(response, '/')

        self.renew_app()
        response = self.app.get(reverse('feeds:unread'))
        self.assertContains(response, 'Username or Email')

    def test_register_subtome(self):
        url = reverse('bookmarklet')
        response = self.app.get(url, user='test')
        self.assertContains(response, 'Subtome')
        self.assertContains(response, 'iframe')
