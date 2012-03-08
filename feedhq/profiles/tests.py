from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase

from ..feeds.models import Category


class ProfilesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('test', 'test@example.com', 'pass')
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
        feed = cat.feeds.create(name='Test Feed',
                                url='http://example.com/test.atom')
        response = self.client.get(url)
        self.assertContains(response, 'xmlUrl="http://example.com/test.atom"')
