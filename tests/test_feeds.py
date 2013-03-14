# -*- coding: utf-8 -*-
import feedparser
import json
import os

from StringIO import StringIO

from django_push.subscriber.signals import updated
from httplib2 import Response
from mock import patch
from requests import Response as _Response
from rq.timeouts import JobTimeoutException

from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from feedhq.feeds.models import Category, Feed, Entry, Favicon, UniqueFeed
from feedhq.feeds.tasks import update_feed
from feedhq.feeds.utils import FAVICON_FETCHER, USER_AGENT

from . import FeedHQTestCase as TestCase

TEST_DATA = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')


def test_file(name):
    return os.path.join(TEST_DATA, name)


def responses(code, path=None, redirection=None,
              headers={'Content-Type': 'text/xml'}):
    response = _Response()
    response.status_code = code
    if path is not None:
        with open(test_file(path), 'r') as f:
            response.raw = StringIO(f.read())
    if redirection is not None:
        temp = _Response()
        temp.status_code = 301 if 'permanent' in redirection else 302
        temp.url = path
        response.history.append(temp)
        response.url = redirection
    response.headers = headers
    return response


class BaseTests(TestCase):
    """Tests that do not require specific setup"""
    @patch('requests.get')
    def test_welcome_page(self, get):
        self.user = User.objects.create_user('testuser',
                                             'foo@example.com',
                                             'pass')
        self.client.login(username='testuser', password='pass')
        url = reverse('feeds:home')
        response = self.client.get(url)
        self.assertContains(response, 'Getting started')
        cat = self.user.categories.create(name='Foo', slug='foo')

        get.return_value = responses(304)
        feed = Feed(name='yo', url='http://example.com/feed', category=cat)
        feed.save()

        response = self.client.get(url)
        self.assertNotContains(response, 'Getting started')

    def test_bookmarklet(self):
        url = reverse('feeds:bookmarklet')
        response = self.client.get(url)
        self.assertContains(response, 'Subscribe on FeedHQ')


class TestFeeds(TestCase):
    @patch("requests.get")
    def setUp(self, get):
        """Main stuff we need for testing the app - this is mainly for signed
        in users."""
        # We'll need a user...
        self.user = User.objects.create_user('testuser',
                                             'foo@example.com',
                                             'pass')
        # ... a category...
        self.cat = Category.objects.create(name='Cat', slug='cat',
                                           user=self.user,
                                           delete_after='never')

        # ... and a feed.
        response = _Response()
        response.status_code = 304
        get.return_value = response
        self.feed = self.cat.feeds.create(name='Test Feed', url='sw-all.xml')
        get.assert_called_with(
            'sw-all.xml',
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        # The user is logged in
        self.client.login(username='testuser', password='pass')

    def test_category_model(self):
        """Behaviour of the ``Category`` model"""
        cat = Category(name='New Cat', slug='new-cat', user=self.user)
        cat.save()

        cat_from_db = Category.objects.get(pk=cat.id)

        # __unicode__
        self.assertEqual('%s' % cat_from_db, 'New Cat')

        # get_absolute_url()
        self.assertEqual('/category/new-cat/', cat_from_db.get_absolute_url())

    @patch('requests.get')
    def test_feed_model(self, get):
        """Behaviour of the ``Feed`` model"""
        get.return_value = responses(200, 'rss20.xml')
        feed = self.cat.feeds.create(name='RSS test', url='rss20.xml')
        feed.save()
        self.cat.delete_after = 'never'
        self.cat.save()

        feed_from_db = Feed.objects.get(pk=feed.id)

        # __unicode__
        self.assertEqual('%s' % feed_from_db, 'RSS test')

        # get_absolute_url()
        self.assertEqual('/feed/%s/' % feed.id, feed.get_absolute_url())

        # update()
        update_feed(feed.url, use_etags=False)

        unique_feed = UniqueFeed.objects.get(url=feed.url)
        self.assertEqual(unique_feed.title, 'Sample Feed')
        self.assertEqual(unique_feed.link, 'http://example.org/')

        feed = Feed.objects.get(pk=feed.id)
        self.assertEqual(feed.entries.count(), 1)
        self.assertEqual(feed.entries.all()[0].title, 'First item title')

    @patch('requests.get')
    def test_entry_model(self, get):
        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)
        title = 'RE2: a principled approach to regular expression matching'
        entry = Entry.objects.get(title=title)

        # __unicode__
        self.assertEqual('%s' % entry, title)

        # get_link()
        self.assertEqual(entry.get_link(), entry.link)
        # Setting permalink
        entry.permalink = 'http://example.com/some-url'
        self.assertEqual(entry.get_link(), entry.permalink)

    @patch('requests.get')
    def test_ctype(self, get):
        # Updatefeed doesn't fail if content-type is missing
        get.return_value = responses(200, self.feed.url, headers={})
        update_feed(self.feed.url, use_etags=False)
        get.assert_called_with(
            self.feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        get.return_value = responses(200, self.feed.url,
                                     headers={'Content-Type': None})
        update_feed(self.feed.url, use_etags=False)
        get.assert_called_with(
            self.feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

    @patch('requests.get')
    def test_permanent_redirects(self, get):
        """Updating the feed if there's a permanent redirect"""
        get.return_value = responses(
            200, redirection='permanent-atom10.xml',
            headers={'Content-Type': 'application/rss+xml'})
        feed = self.cat.feeds.create(name='Permanent', url='permanent.xml')
        feed = Feed.objects.get(pk=feed.id)
        self.assertEqual(feed.url, 'permanent-atom10.xml')

    @patch('requests.get')
    def test_temporary_redirect(self, get):
        """Don't update the feed if the redirect is not 301"""
        get.return_value = responses(
            200, redirection='atom10.xml',
            headers={'Content-Type': 'application/rss+xml'})
        feed = self.cat.feeds.create(name='Temp', url='temp.xml')
        feed = Feed.objects.get(pk=feed.id)
        self.assertEqual(feed.url, 'temp.xml')
        get.assert_called_with(
            'temp.xml', timeout=10,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER},
        )

    @patch('requests.get')
    def test_content_handling(self, get):
        """The content section overrides the subtitle section"""
        get.return_value = responses(200, 'atom10.xml')
        self.cat.feeds.create(name='Content', url='atom10.xml')
        entry = Entry.objects.get()
        self.assertEqual(entry.sanitized_content(),
                         "<div>Watch out for <span> nasty tricks</span></div>")

    @patch('requests.get')
    def test_gone(self, get):
        """Muting the feed if the status code is 410"""
        get.return_value = responses(410)
        feed = self.cat.feeds.create(name='Gone', url='gone.xml')
        feed = UniqueFeed.objects.get(url='gone.xml')
        self.assertTrue(feed.muted)

    @patch('requests.get')
    def test_errors(self, get):
        for code in [400, 401, 403, 404, 500, 502, 503]:
            get.return_value = responses(code)
            feed = UniqueFeed.objects.get(url=self.feed.url)
            self.assertFalse(feed.muted)
            self.assertEqual(feed.error, None)
            self.assertEqual(feed.backoff_factor, 1)

            update_feed(self.feed.url, use_etags=False)

            feed = UniqueFeed.objects.get(url=self.feed.url)
            self.assertFalse(feed.muted)
            self.assertEqual(feed.error, str(code))
            self.assertEqual(feed.backoff_factor, 2)

            # Restore status for next iteration
            feed.backoff_factor = 1
            feed.error = None
            feed.save()

    @patch('requests.get')
    def test_backoff(self, get):
        get.return_value = responses(502)
        feed = UniqueFeed.objects.get(url=self.feed.url)
        self.assertEqual(feed.error, None)
        self.assertEqual(feed.backoff_factor, 1)

        for i in range(12):
            update_feed(self.feed.url, use_etags=False)
            feed = UniqueFeed.objects.get(url=self.feed.url)
            self.assertFalse(feed.muted)
            self.assertEqual(feed.error, '502')
            self.assertEqual(feed.backoff_factor, min(i + 2, 10))

    @patch('requests.get')
    def test_no_date_and_304(self, get):
        """If the feed does not have a date, we'll have to find one.
        Also, since we update it twice, the 2nd time it's a 304 response."""
        get.return_value = responses(200, 'no-date.xml')
        feed = self.cat.feeds.create(name='Django Community',
                                     url='no-date.xml')

        # Update the feed twice and make sure we don't index the content twice
        update_feed(feed.url, use_etags=False)
        feed1 = Feed.objects.get(pk=feed.id)
        count1 = feed1.entries.count()

        update_feed(feed1.url, use_etags=False)
        feed2 = Feed.objects.get(pk=feed1.id)
        count2 = feed2.entries.count()

        self.assertEqual(count1, count2)

    @patch('requests.get')
    def test_no_link(self, get):
        get.return_value = responses(200, 'rss20.xml')
        self.feed.url = 'rss20.xml'
        self.feed.save()
        update_feed(self.feed.url, use_etags=False)
        self.assertEqual(Entry.objects.count(), 1)

        get.return_value = responses(200, 'no-link.xml')
        self.feed.url = 'no-link.xml'
        self.feed.save()
        update_feed(self.feed.url, use_etags=False)
        self.assertEqual(Entry.objects.count(), 1)

    @patch('requests.get')
    def test_multiple_objects(self, get):
        """Duplicates are removed at the next update"""
        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)
        entry = self.feed.entries.all()[0]
        entry.id = None
        entry.save()
        entry.id = None
        entry.save()
        self.assertEqual(self.feed.entries.count(), 32)
        update_feed(self.feed.url, use_etags=False)
        self.assertEqual(self.feed.entries.count(), 30)

    def test_uniquefeed_deletion(self):
        f = UniqueFeed.objects.create(url='example.com')
        self.assertEqual(UniqueFeed.objects.count(), 2)
        UniqueFeed.objects.update_feed(f.url, use_etags=False)
        self.assertEqual(UniqueFeed.objects.count(), 1)

    def test_entry_model_behaviour(self):
        """Behaviour of the `Entry` model"""
        entry = Entry(feed=self.feed, title='My title', user=self.user,
                      date=timezone.now())
        entry.save()

        # __unicode__
        self.assertEqual('%s' % entry, 'My title')

        # get_absolute_url()
        self.assertEqual('/entries/%s/' % entry.id, entry.get_absolute_url())

    @patch('requests.get')
    def test_task_timeout_handling(self, get):
        get.side_effect = JobTimeoutException
        self.assertEqual(UniqueFeed.objects.get().backoff_factor, 1)
        update_feed(self.feed.url, use_etags=False)
        self.assertEqual(UniqueFeed.objects.get().backoff_factor, 2)

    ### Views ###
    def test_homepage(self):
        """The homepage from a logged in user"""
        response = self.client.get(reverse('feeds:home'))
        self.assertContains(response, 'Home')
        self.assertContains(response, 'testuser')

    def test_unauth_homepage(self):
        """The home page from a logged-out user"""
        self.client.logout()
        response = self.client.get(reverse('feeds:home'))
        self.assertContains(response, 'Sign in')  # login required

    def test_paginator(self):
        response = self.client.get(reverse('feeds:home', args=[5]))
        self.assertContains(response, 'Home')

    def test_category(self):
        url = reverse('feeds:category', args=['cat'])
        response = self.client.get(url)
        self.assertContains(response, 'Cat')

    def test_feed(self):
        url = reverse('feeds:feed', args=[self.feed.id])
        response = self.client.get(url)

        expected = '<a href="%sunread/">unread <span class="ct">0</span></a>'
        expected = expected % self.feed.get_absolute_url()
        self.assertContains(response, expected)

    def test_only_unread(self):
        url = reverse('feeds:unread_category', args=['cat'])
        response = self.client.get(url)

        self.assertContains(response, 'Cat')
        self.assertContains(response, 'all <span class="ct">')

    def test_add_category(self):
        url = reverse('feeds:add_category')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        bad_data = {'name': ''}
        response = self.client.post(url, bad_data)
        self.assertContains(response, 'errorlist')

        data = {'name': 'New Name', 'color': 'red', 'delete_after': '1day'}
        response = self.client.post(url, data)
        self.assertRedirects(response, '/category/new-name/')

        # Adding a category with the same name. The slug will be different
        response = self.client.post(url, data)
        self.assertRedirects(response, '/category/new-name-1/')

        # Now we add a category named 'add', which is a conflicting URL
        data = {'name': 'Add', 'color': 'red', 'delete_after': '1day'}
        response = self.client.post(url, data)
        self.assertRedirects(response, '/category/add-1/')

        # Add a category with non-ASCII names, slugify should cope
        data = {'name': u'北京', 'color': 'red', 'delete_after': '1day'}
        response = self.client.post(url, data)
        self.assertRedirects(response, '/category/unknown/')
        response = self.client.post(url, data)
        self.assertRedirects(response, '/category/unknown-1/')
        response = self.client.post(url, data)
        self.assertRedirects(response, '/category/unknown-2/')

    def test_delete_category(self):
        url = reverse('feeds:delete_category', args=['cat'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Category.objects.count(), 1)
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Category.objects.count(), 0)

    def test_edit_category(self):
        url = reverse('feeds:edit_category', args=['cat'])
        response = self.client.get(url)
        self.assertContains(response, 'Edit Cat')

        data = {'name': 'New Name', 'color': 'blue', 'delete_after': '2days'}
        response = self.client.post(url, data)
        self.assertContains(response,
                            'New Name has been successfully updated')

    @patch('requests.get')
    def test_add_feed(self, get):
        url = reverse('feeds:add_feed')
        response = self.client.get(url)
        self.assertContains(response, 'Add a feed')

        bad_data = {'name': 'Lulz'}  # there is no URL / category
        response = self.client.post(url, bad_data)
        self.assertContains(response, 'errorlist')

        data = {'name': 'Bobby', 'url': 'http://example.com/feed.xml',
                'category': self.cat.id}
        get.return_value = responses(304)
        response = self.client.post(url, data)
        self.assertRedirects(response, '/category/cat/')

    def test_feed_url_validation(self):
        url = reverse('feeds:add_feed')
        data = {
            'name': 'Test',
            'url': 'ftp://example.com',
            'category': self.cat.pk,
        }
        response = self.client.post(url, data)
        self.assertFormError(
            response, 'form', 'url',
            "Invalid URL scheme: 'ftp'. Only HTTP and HTTPS are supported.",
        )

        for invalid_url in ['http://localhost:8000', 'http://localhost',
                            'http://127.0.0.1']:
            data['url'] = invalid_url
            response = self.client.post(url, data)
            self.assertFormError(response, 'form', 'url', "Invalid URL.")

    def test_edit_feed(self):
        url = reverse('feeds:edit_feed', args=[self.feed.id])
        response = self.client.get(url)
        self.assertContains(response, 'Test Feed')

        bad_data = {'feed-name': 'New test name'}
        response = self.client.post(url, bad_data)
        self.assertContains(response, 'errorlist')

        data = {'name': 'New Name',
                'url': 'http://example.com/newfeed.xml',
                'category': self.cat.id}
        response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, 'New Name has been successfully updated')

    def test_delete_feed(self):
        url = reverse('feeds:delete_feed', args=[self.feed.id])
        response = self.client.get(url)
        self.assertContains(response, 'Delete')
        self.assertContains(response, self.feed.name)

        self.assertEqual(Feed.objects.count(), 1)
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Feed.objects.count(), 0)
        # Redirects to home so useless to test

    def test_invalid_page(self):
        # We need more than 25 entries
        update_feed(self.feed.url)
        url = reverse('feeds:home', args=[12000])  # that page doesn't exist
        response = self.client.get(url)
        self.assertContains(response, '<a href="/" class="current">')

    # This is called by other tests
    def _test_entry(self, from_url):
        self.assertEqual(self.client.get(from_url).status_code, 200)

        e = Entry.objects.get(title="jacobian's django-deployment-workshop")
        url = reverse('feeds:item', args=[e.pk])
        response = self.client.get(url)
        self.assertContains(response, "jacobian's django-deployment-workshop")

    @patch('requests.get')
    def test_entry(self, get):
        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)

        url = reverse('feeds:home')
        self._test_entry(url)

        url = reverse('feeds:unread')
        self._test_entry(url)

        url = reverse('feeds:category', args=[self.cat.slug])
        self._test_entry(url)

        url = reverse('feeds:unread_category', args=[self.cat.slug])
        self._test_entry(url)

        url = reverse('feeds:feed', args=[self.feed.pk])
        self._test_entry(url)

        url = reverse('feeds:unread_feed', args=[self.feed.pk])
        self._test_entry(url)

    @patch('requests.get')
    def test_last_entry(self, get):
        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)

        last_item = self.user.entries.order_by('date')[0]
        url = reverse('feeds:item', args=[last_item.id])
        response = self.client.get(url)
        self.assertNotContains(response, 'Next →')

    def test_img(self):
        entry = Entry.objects.create(
            feed=self.feed,
            title="Random title",
            subtitle='<img src="/favicon.png">',
            permalink='http://example.com',
            date=timezone.now(),
            user=self.user,
        )
        url = reverse('feeds:item', args=[entry.pk])
        response = self.client.get(url)
        self.assertContains(response, 'External media is hidden')
        self.assertNotContains(response, '<img src="/favicon.png">')
        self.assertEqual(Feed.objects.get(pk=self.feed.pk).media_safe, False)
        response = self.client.post(url, {'action': 'images', 'once': 'once'})
        self.assertContains(response, 'Always display external media')
        self.assertContains(response, '<img src="/favicon.png">')
        self.assertEqual(Feed.objects.get(pk=self.feed.pk).media_safe, False)
        response = self.client.post(url, {'action': 'images',
                                          'always': 'always'})
        self.assertContains(response, 'Disable external media')
        self.assertContains(response, '<img src="/favicon.png">')
        self.assertEqual(Feed.objects.get(pk=self.feed.pk).media_safe, True)
        response = self.client.post(url, {'action': 'images',
                                          'never': 'never'})
        self.assertNotContains(response, 'Disable external media')
        self.assertEqual(Feed.objects.get(pk=self.feed.pk).media_safe, False)

    @patch('requests.get')
    def test_opml_import(self, get):
        url = reverse('feeds:import_feeds')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        get.return_value = responses(304)

        with open(test_file('sample.opml'), 'r') as opml_file:
            data = {'file': opml_file}
            response = self.client.post(url, data, follow=True)

        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, '2 feeds have been imported')
        self.assertEqual(Category.objects.filter(name='Imported').count(), 1)

        # Re-import
        with open(test_file('sample.opml'), 'r') as opml_file:
            data = {'file': opml_file}
            response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, '0 feeds have been imported')

    @patch('requests.get')
    def test_categories_in_opml(self, get):
        url = reverse('feeds:import_feeds')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        get.return_value = responses(304)

        with open(test_file('categories.opml'), 'r') as opml_file:
            data = {'file': opml_file}
            response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, '20 feeds have been imported')
        self.assertEqual(self.user.categories.count(), 8)
        with self.assertRaises(Category.DoesNotExist):
            self.user.categories.get(name='Imported')
        with self.assertRaises(Feed.DoesNotExist):
            Feed.objects.get(
                category__in=self.user.categories.all(),
                name='No title',
            )

        for c in Category.objects.all():
            c.get_absolute_url()

    def test_dashboard(self):
        url = reverse('feeds:dashboard')
        response = self.client.get(url)
        self.assertContains(response, 'Dashboard')

    @patch('requests.get')
    def test_unread_count(self, get):
        """Unread feed count everywhere"""
        url = reverse('profile')
        response = self.client.get(url)
        self.assertContains(
            response,
            '<a class="unread" title="Unread entries" href="/unread/">0</a>'
        )

        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)

        response = self.client.get(url)
        self.assertContains(
            response,
            '<a class="unread" title="Unread entries" href="/unread/">30</a>'
        )

    @patch('requests.get')
    def test_mark_as_read(self, get):
        url = reverse('feeds:unread')
        response = self.client.get(url)
        self.assertNotContains(response, 'Mark all as read')

        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)

        response = self.client.get(url)
        self.assertContains(response, 'Mark all as read')

        data = {'action': 'read'}
        response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, '30 entries have been marked as read')

    @patch('requests.get')
    @patch('oauth2.Client')
    def test_add_to_readability(self, Client, get):
        client = Client.return_value
        r = Response({
            'status': 202,
            'reason': 'Accepted',
            'location': '/api/rest/v1/bookmarks/119',
            'x-article-location': '/api/rest/v1/articles/xj28dwkx',
        })
        value = json.dumps({'article': {'id': 'foo'}})
        client.request.return_value = [r, value]
        self.user.read_later = 'readability'
        self.user.read_later_credentials = json.dumps({
            'oauth_token': 'token',
            'oauth_token_secret': 'token secret',
        })
        self.user.save()

        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)
        get.assert_called_with(
            'sw-all.xml',
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        entry_pk = Entry.objects.all()[0].pk
        url = reverse('feeds:item', args=[entry_pk])
        response = self.client.get(url)
        self.assertContains(response, "Add to Readability")

        data = {'action': 'read_later'}
        response = self.client.post(url, data)
        client.request.assert_called_with('/api/rest/v1/bookmarks/119',
                                          method='GET')
        self.assertEqual(Entry.objects.get(pk=entry_pk).read_later_url,
                         'https://www.readability.com/articles/foo')
        response = self.client.get(url)
        self.assertNotContains(response, "Add to Instapaper")

    @patch("requests.get")
    @patch('oauth2.Client')
    def test_add_to_instapaper(self, Client, get):
        client = Client.return_value
        r = Response({'status': 200})
        client.request.return_value = [
            r,
            json.dumps([{'type': 'bookmark', 'bookmark_id': 12345,
                         'title': 'Some bookmark',
                         'url': 'http://example.com/some-bookmark'}])
        ]

        get.return_value = responses(200, self.feed.url)

        update_feed(self.feed.url, use_etags=False)
        get.assert_called_with(
            'sw-all.xml',
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        self.user.read_later = 'instapaper'
        self.user.read_later_credentials = json.dumps({
            'oauth_token': 'token',
            'oauth_token_secret': 'token secret',
        })
        self.user.save()

        entry_pk = Entry.objects.all()[0].pk
        url = reverse('feeds:item', args=[entry_pk])
        response = self.client.get(url)
        self.assertContains(response, "Add to Instapaper")

        data = {'action': 'read_later'}
        response = self.client.post(url, data)
        body = 'url=http%3A%2F%2Fsimonwillison.net%2F2010%2FMar%2F12%2Fre2%2F'
        client.request.assert_called_with(
            'https://www.instapaper.com/api/1/bookmarks/add',
            body=body,
            method='POST',
        )
        self.assertEqual(Entry.objects.get(pk=entry_pk).read_later_url,
                         'https://www.instapaper.com/read/12345')
        response = self.client.get(url)
        self.assertNotContains(response, "Add to Instapaper")

    @patch('requests.get')
    @patch('requests.post')
    def test_add_to_readitlaterlist(self, post, get):
        data = {'action': 'read_later'}
        self.user.read_later = 'readitlater'
        self.user.read_later_credentials = json.dumps({'username': 'foo',
                                                       'password': 'bar'})
        self.user.save()

        get.return_value = responses(200, self.feed.url)
        update_feed(self.feed.url, use_etags=False)
        get.assert_called_with(
            'sw-all.xml',
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        url = reverse('feeds:item', args=[Entry.objects.all()[0].pk])
        response = self.client.get(url)
        self.assertContains(response, 'Add to Read it later')
        response = self.client.post(url, data)
        # Read it Later doesn't provide the article URL so we can't display a
        # useful link
        self.assertContains(response, "added to your reading list")
        post.assert_called_with(
            'https://readitlaterlist.com/v2/add',
            data={u'username': u'foo',
                  'url': u'http://simonwillison.net/2010/Mar/12/re2/',
                  'apikey': 'test read it later API key',
                  u'password': u'bar',
                  'title': (u'RE2: a principled approach to regular '
                            u'expression matching')},
        )

    @patch('requests.get')
    def test_pubsubhubbub_handling(self, get):
        url = 'http://bruno.im/atom/tag/django-community/'
        get.return_value = responses(304)
        feed = self.cat.feeds.create(url=url, name='Bruno')
        get.assert_called_with(
            url, headers={'User-Agent': USER_AGENT % '1 subscriber',
                          'Accept': feedparser.ACCEPT_HEADER},
            timeout=10)

        self.assertEqual(feed.entries.count(), 0)
        path = test_file('bruno.im.atom')
        parsed = feedparser.parse(path)
        updated.send(sender=None, notification=parsed)
        self.assertEqual(feed.entries.count(), 5)

        # Check content handling
        for entry in feed.entries.all():
            self.assertTrue(len(entry.subtitle) > 2400)

        # Check date handling
        self.assertEqual(feed.entries.filter(date__year=2011).count(), 3)
        self.assertEqual(feed.entries.filter(date__year=2012).count(), 2)

    @patch('requests.get')
    def test_bookmarklet_post(self, get):
        url = '/subscribe/'  # hardcoded in the JS file
        with open(test_file('bruno-head.html'), 'r') as f:
            data = {
                'source': 'http://bruno.im/',
                'html': f.read(),
            }
            response = self.client.post(url, data)
        self.assertContains(response, 'value="http://bruno.im/atom/latest/"')

        token = response.content.split("csrfmiddlewaretoken' value='")[1]
        token = token.split("' />", 1)[0]

        url = reverse('feeds:bookmarklet_subscribe')
        data = {
            'form-TOTAL_FORMS': 1,
            'form-INITIAL_FORMS': 1,
            'form-0-subscribe': True,
            'form-0-name': 'Bruno.im',
            'form-0-url': 'http://bruno.im/atom/latest/',
            'form-0-category': self.cat.pk,
            'csrfmiddlewaretoken': token,
        }
        self.assertEqual(Feed.objects.count(), 1)

        get.return_value = responses(304)
        response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertEqual(Feed.objects.count(), 2)

    def test_bookmarklet_parsing(self):
        url = reverse('feeds:bookmarklet_subscribe')
        for name, count in [('figaro', 15), ('github', 2), ('techcrunch', 3)]:
            with open(test_file('%s-head.html' % name), 'r') as f:
                response = self.client.post(url, {'html': f.read(),
                                                  'source': 'http://t.com'})
            self.assertContains(response, name)
            self.assertEqual(len(response.content.split(
                '<div class="subscribe_form">'
            )), count + 1)

    def test_get_bookmarklet(self):
        url = reverse('feeds:bookmarklet_subscribe')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response['Accept'], 'POST')

    def test_bookmarklet_no_feed(self):
        url = reverse('feeds:bookmarklet_subscribe')
        response = self.client.post(url, {
            'source': 'http://isitbeeroclock.com/',
            'html': '<link>',
        })
        self.assertContains(response, 'No feed found')
        self.assertContains(response, 'Return to the site')

    @patch('requests.get')
    def test_duplicate(self, get):
        """Adding an entry the user already has marks it as read"""
        get.return_value = responses(200, 'rss20.xml')

        # Creating a feed will update it and assign the entry
        self.cat.feeds.create(url='http://exampleexample.com')

        # Update another feed with the same entry
        update_feed(self.feed.url, use_etags=False)

        self.assertEqual(Entry.objects.count(), 2)
        # One entry is unread
        Entry.objects.get(link="http://example.org/item/1", read=False)
        # Other is read
        Entry.objects.get(link="http://example.org/item/1", read=True)


class FaviconTests(TestCase):
    @patch("requests.get")
    def test_declared_favicon(self, get):
        with open(test_file('bruno.im.png'), 'r') as f:
            fav = f.read()

        class Response:
            status_code = 200
            content = fav
            headers = {'foo': 'bar'}
        get.return_value = Response()
        Favicon.objects.update_favicon('http://example.com/')
        get.assert_called_with(
            'http://example.com/favicon.ico',
            headers={'User-Agent': FAVICON_FETCHER},
            timeout=10,
        )
