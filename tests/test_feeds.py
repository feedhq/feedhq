# -*- coding: utf-8 -*-
import feedparser
import json

from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django_push.subscriber.signals import updated
from django_webtest import WebTest
from httplib2 import Response
from mock import patch

from feedhq.feeds.models import Category, Feed, Entry, UniqueFeed
from feedhq.feeds.tasks import update_feed
from feedhq.feeds.utils import USER_AGENT
from feedhq.profiles.models import User

from .factories import UserFactory, CategoryFactory, FeedFactory, EntryFactory
from . import test_file, responses


class WebBaseTests(WebTest):
    @patch('requests.get')
    def test_welcome_page(self, get):
        get.return_value = responses(304)

        self.user = User.objects.create_user('testuser',
                                             'foo@example.com',
                                             'pass')
        user = UserFactory.create()
        url = reverse('feeds:home')
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'Getting started')
        FeedFactory.create(category__user=user, user=user)
        response = self.app.get(url)
        self.assertNotContains(response, 'Getting started')

    def test_login_required(self):
        url = reverse('feeds:home')
        response = self.app.get(url, headers={'Accept': 'text/*'})
        self.assertEqual(response.status_code, 200)

    def test_homepage(self):
        """The homepage from a logged in user"""
        user = UserFactory.create()
        response = self.app.get(reverse('feeds:home'),
                                user=force_bytes(user.username))
        self.assertContains(response, 'Home')
        self.assertContains(response, user.username)

    def test_unauth_homepage(self):
        """The home page from a logged-out user"""
        response = self.app.get(reverse('feeds:home'))
        self.assertContains(response, 'Sign in')  # login required

    def test_paginator(self):
        user = UserFactory.create()
        response = self.app.get(reverse('feeds:home', args=[5]),
                                user=force_bytes(user.username))
        self.assertContains(response, 'Home')

    def test_category(self):
        user = UserFactory.create()
        CategoryFactory.create(user=user, name=u'Cat yo')
        url = reverse('feeds:category', args=['cat-yo'])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'Cat yo')

    @patch("requests.get")
    def test_only_unread(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        FeedFactory.create(category=category, user=user)
        url = reverse('feeds:unread_category', args=[category.slug])
        response = self.app.get(url, user=force_bytes(user.username))

        self.assertContains(response, category.name)
        self.assertContains(response, 'all <span class="ct">')

    def test_add_category(self):
        user = UserFactory.create()
        url = reverse('feeds:add_category')
        response = self.app.get(url, user=force_bytes(user.username))

        form = response.forms['category']
        response = form.submit()
        self.assertFormError(response, 'form', 'name',
                             ['This field is required.'])

        form['name'] = 'New Name'
        form['color'] = 'red'
        response = form.submit()
        self.assertRedirects(response, '/category/new-name/')

        # Re-submitting the same name fails
        response = form.submit()
        self.assertFormError(response, 'form', 'name',
                             ['A category with this name already exists.'])

        # Adding a category with a name generating the same slug.
        # The slug will be different
        form['name'] = 'New  Name'
        response = form.submit()
        self.assertRedirects(response, '/category/new-name-1/')

        # Now we add a category named 'add', which is a conflicting URL
        form['name'] = 'add'
        response = form.submit()
        self.assertRedirects(response, '/category/add-1/')

        # Add a category with non-ASCII names, slugify should cope
        form['name'] = u'北京'
        response = form.submit()
        self.assertRedirects(response, '/category/unknown/')
        form['name'] = u'北'
        response = form.submit()
        self.assertRedirects(response, '/category/unknown-1/')
        form['name'] = u'京'
        response = form.submit()
        self.assertRedirects(response, '/category/unknown-2/')

    def test_delete_category(self):
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        url = reverse('feeds:delete_category', args=[category.slug])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Category.objects.count(), 1)
        form = response.forms['delete']
        response = form.submit().follow()
        self.assertEqual(Category.objects.count(), 0)

    @patch("requests.get")
    def test_feed(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        feed = FeedFactory.create(category__user=user, user=user)
        url = reverse('feeds:feed', args=[feed.pk])
        response = self.app.get(url, user=force_bytes(user.username))

        expected = (
            '<a href="{0}unread/">unread <span class="ct">0</span></a>'
        ).format(feed.get_absolute_url())
        self.assertContains(response, expected)

    def test_edit_category(self):
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        url = reverse('feeds:edit_category', args=[category.slug])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, u'Edit {0}'.format(category.name))

        form = response.forms['category']
        form['name'] = 'New Name'
        form['color'] = 'blue'

        response = form.submit().follow()
        self.assertContains(response,
                            'New Name has been successfully updated')

    @patch('requests.get')
    def test_add_feed(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)

        url = reverse('feeds:add_feed')
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'Add a feed')

        form = response.forms['feed']
        form['name'] = 'Lulz'
        response = form.submit()  # there is no URL
        self.assertFormError(response, 'form', 'url',
                             ['This field is required.'])

        form['name'] = 'Bobby'
        form['url'] = 'http://example.com/feed.xml'
        form['category'] = category.pk
        response = form.submit()
        self.assertFormError(response, 'form', 'url', [
            "Invalid response code from URL: HTTP 304.",
        ])
        get.return_value = responses(200, 'categories.opml')
        response = form.submit()
        self.assertFormError(response, 'form', 'url', [
            "This URL doesn't seem to be a valid feed.",
        ])

        get.return_value = responses(200, 'bruno.im.png')
        response = form.submit()
        self.assertFormError(response, 'form', 'url', [
            "This URL doesn't seem to be a valid feed.",
        ])

        cache_key = "lock:feed_check:{0}".format(user.pk)
        cache._client.set(cache_key, user.pk)
        response = form.submit()
        self.assertFormError(response, 'form', 'url', [
            "This action can only be done one at a time.",
        ])
        cache._client.delete(cache_key)

        get.return_value = responses(200, 'brutasse.atom')
        response = form.submit()
        self.assertRedirects(response, category.get_absolute_url())
        response.follow()

        response = form.submit()
        self.assertFormError(
            response, 'form', 'url',
            ["It seems you're already subscribed to this feed."])

        # Provide initial params via ?feed=foo&name=bar
        response = self.app.get(url, {'feed': 'https://example.com/blog/atom',
                                      'name': 'Some Example Blog'})
        self.assertContains(response, 'value="https://example.com/blog/atom"')
        self.assertContains(response, 'value="Some Example Blog"')

    def test_feed_url_validation(self):
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        url = reverse('feeds:add_feed')
        response = self.app.get(url, user=force_bytes(user.username))

        form = response.forms['feed']
        form['name'] = 'Test'
        form['url'] = 'ftp://example.com'
        form['category'] = category.pk

        response = form.submit()
        self.assertFormError(
            response, 'form', 'url',
            "Invalid URL scheme: 'ftp'. Only HTTP and HTTPS are supported.",
        )

        for invalid_url in ['http://localhost:8000', 'http://localhost',
                            'http://127.0.0.1']:
            form['url'] = invalid_url
            response = form.submit()
            self.assertFormError(response, 'form', 'url', "Invalid URL.")

    @patch("requests.get")
    def test_edit_feed(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        feed = FeedFactory.create(user=user)
        url = reverse('feeds:edit_feed', args=[feed.pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, feed.name)

        form = response.forms['feed']

        form['name'] = 'New Name'
        form['url'] = 'http://example.com/newfeed.xml'
        get.return_value = responses(200, 'brutasse.atom')
        response = form.submit().follow()
        self.assertContains(response, 'New Name has been successfully updated')

        cat = CategoryFactory.create(user=user)
        response = self.app.get(url, user=force_bytes(user.username))
        form = response.forms['feed']
        form['category'] = cat.pk
        response = form.submit().follow()
        self.assertContains(response, 'New Name has been successfully updated')
        self.assertEqual(Feed.objects.get().category_id, cat.pk)

    @patch("requests.get")
    def test_delete_feed(self, get):
        get.return_value = responses(304)

        user = UserFactory.create()
        feed = FeedFactory.create(category__user=user, user=user)
        url = reverse('feeds:delete_feed', args=[feed.pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'Delete')
        self.assertContains(response, feed.name)

        self.assertEqual(Feed.objects.count(), 1)
        response = response.forms['delete'].submit()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Feed.objects.count(), 0)
        # Redirects to home so useless to test

    @patch("requests.get")
    def test_invalid_page(self, get):
        get.return_value = responses(304)
        # We need more than 25 entries
        user = UserFactory.create()
        FeedFactory.create(category__user=user, user=user)
        url = reverse('feeds:home', args=[12000])  # that page doesn't exist
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, '<a href="/" class="current">')

    # This is called by other tests
    def _test_entry(self, from_url, user):
        self.assertEqual(self.app.get(
            from_url, user=force_bytes(user.username)).status_code, 200)

        e = Entry.objects.get(title="jacobian's django-deployment-workshop")
        url = reverse('feeds:item', args=[e.pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, "jacobian's django-deployment-workshop")

    @patch('requests.get')
    def test_entry(self, get):
        user = UserFactory.create()
        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create(category__user=user, user=user)

        url = reverse('feeds:home')
        self._test_entry(url, user)

        url = reverse('feeds:unread')
        self._test_entry(url, user)

        url = reverse('feeds:category', args=[feed.category.slug])
        self._test_entry(url, user)

        url = reverse('feeds:unread_category', args=[feed.category.slug])
        self._test_entry(url, user)

        url = reverse('feeds:feed', args=[feed.pk])
        self._test_entry(url, user)

        url = reverse('feeds:unread_feed', args=[feed.pk])
        self._test_entry(url, user)

        feed.category = None
        feed.save()
        self._test_entry(url, user)

    @patch('requests.get')
    def test_last_entry(self, get):
        user = UserFactory.create()
        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create(category__user=user, user=user)

        with self.assertNumQueries(2):
            update_feed(feed.url)
        self.assertEqual(Feed.objects.get().unread_count,
                         user.entries.filter(read=False).count())

        last_item = user.entries.order_by('date')[0]
        url = reverse('feeds:item', args=[last_item.pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertNotContains(response, 'Next →')

    def test_not_mocked(self):
        with self.assertRaises(ValueError):
            FeedFactory.create()

    @patch("requests.get")
    def test_img(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        feed = FeedFactory.create(category__user=user, url='http://exmpl.com',
                                  user=user)
        entry = Entry.objects.create(
            feed=feed,
            title="Random title",
            subtitle='<img src="/favicon.png">',
            link='http://example.com',
            date=timezone.now(),
            user=user,
        )
        url = reverse('feeds:item', args=[entry.pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'External media is hidden')
        self.assertNotContains(response,
                               '<img src="http://exmpl.com/favicon.png">')
        self.assertEqual(Feed.objects.get(pk=feed.pk).media_safe, False)

        form = response.forms['images']
        response = form.submit(name='once')
        self.assertContains(response, 'Always display external media')
        self.assertContains(response,
                            '<img src="http://exmpl.com/favicon.png">')
        self.assertEqual(Feed.objects.get(pk=feed.pk).media_safe, False)
        form = response.forms['images']
        response = form.submit(name='always')
        self.assertContains(response, 'Disable external media')
        self.assertContains(response,
                            '<img src="http://exmpl.com/favicon.png">')
        self.assertEqual(Feed.objects.get(pk=feed.pk).media_safe, True)
        form = response.forms['images']
        response = form.submit(name='never')
        self.assertNotContains(response, 'Disable external media')
        self.assertEqual(Feed.objects.get(pk=feed.pk).media_safe, False)

        user.allow_media = True
        user.save(update_fields=['allow_media'])
        response = form.submit(name='never')
        self.assertFalse('images' in response.forms)
        self.assertContains(response,
                            '<img src="http://exmpl.com/favicon.png">')

    @patch('requests.get')
    def test_opml_import(self, get):
        user = UserFactory.create()
        url = reverse('feeds:import_feeds')
        response = self.app.get(url, user=force_bytes(user.username))

        get.return_value = responses(304)
        form = response.forms['import']

        with open(test_file('sample.opml'), 'r') as opml_file:
            form['file'] = 'sample.opml', opml_file.read()
        response = form.submit().follow()

        self.assertContains(response, '2 feeds have been imported')

        # Re-import
        with open(test_file('sample.opml'), 'r') as opml_file:
            form['file'] = 'sample.opml', opml_file.read()
        response = form.submit().follow()
        self.assertContains(response, '0 feeds have been imported')

        # Import an invalid thing
        form['file'] = 'invalid', "foobar"
        response = form.submit()
        self.assertFormError(response, 'form', 'file', [
            "This file doesn't seem to be a valid OPML file."
        ])

        # Empty file
        form['file'] = 'name', ""
        response = form.submit()
        self.assertFormError(response, 'form', 'file', [
            "The submitted file is empty."
        ])

    @patch('requests.get')
    def test_categories_in_opml(self, get):
        user = UserFactory.create()
        url = reverse('feeds:import_feeds')
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertEqual(response.status_code, 200)

        get.return_value = responses(304)

        form = response.forms["import"]

        with open(test_file('categories.opml'), 'r') as opml_file:
            form['file'] = 'categories.opml', opml_file.read()

        response = form.submit().follow()
        self.assertContains(response, '20 feeds have been imported')
        self.assertEqual(user.categories.count(), 7)
        with self.assertRaises(Category.DoesNotExist):
            user.categories.get(name='Imported')
        with self.assertRaises(Feed.DoesNotExist):
            Feed.objects.get(
                category__in=user.categories.all(),
                name='No title',
            )

        for c in Category.objects.all():
            c.get_absolute_url()

    @patch('requests.get')
    def test_dashboard(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        url = reverse('feeds:dashboard')
        FeedFactory.create(category=None, user=user)
        for i in range(5):
            FeedFactory.create(category__user=user, user=user)
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'Dashboard')

    @patch('requests.get')
    def test_unread_count(self, get):
        """Unread feed count everywhere"""
        user = UserFactory.create()
        url = reverse('profile')
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(
            response,
            '<a class="unread" title="Unread entries" href="/unread/">0</a>'
        )

        get.return_value = responses(200, 'sw-all.xml')
        FeedFactory.create(category__user=user, user=user)

        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(
            response,
            '<a class="unread" title="Unread entries" href="/unread/">30</a>'
        )

    @patch('requests.get')
    def test_mark_as_read(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        feed = FeedFactory.create(category__user=user, user=user)
        url = reverse('feeds:unread')
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertNotContains(response, 'Mark all as read')

        get.return_value = responses(200, 'sw-all.xml')
        update_feed(feed.url)

        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'Mark all as read')

        form = response.forms['read']
        response = form.submit()
        self.assertRedirects(response, url)
        response = response.follow()
        self.assertContains(response, '30 entries have been marked as read')

        self.assertEqual(user.entries.filter(read=False).count(), 0)
        self.assertEqual(user.entries.filter(read=True).count(), 30)

        form = response.forms['undo']
        response = form.submit()
        self.assertRedirects(response, url)
        response = response.follow()
        self.assertContains(response, "30 entries have been marked as unread")

        self.assertEqual(user.entries.filter(read=False).count(), 30)
        self.assertEqual(user.entries.filter(read=True).count(), 0)

    @patch('requests.get')
    @patch('oauth2.Client')
    def test_add_to_readability(self, Client, get):  # noqa
        client = Client.return_value
        r = Response({
            'status': 202,
            'reason': 'Accepted',
            'location': '/api/rest/v1/bookmarks/119',
            'x-article-location': '/api/rest/v1/articles/xj28dwkx',
        })
        value = json.dumps({'article': {'id': 'foo'}})
        client.request.return_value = [r, value]

        user = UserFactory.create(
            read_later='readability',
            read_later_credentials=json.dumps({
                'oauth_token': 'token',
                'oauth_token_secret': 'token secret',
            }),
        )

        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create(category__user=user, user=user)
        get.assert_called_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        entry_pk = Entry.objects.all()[0].pk
        url = reverse('feeds:item', args=[entry_pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, "Add to Readability")

        form = response.forms['read-later']
        response = form.submit()
        client.request.assert_called_with('/api/rest/v1/bookmarks/119',
                                          method='GET')
        self.assertEqual(Entry.objects.get(pk=entry_pk).read_later_url,
                         'https://www.readability.com/articles/foo')
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertNotContains(response, "Add to Instapaper")

    @patch("requests.get")
    @patch('oauth2.Client')
    def test_add_to_instapaper(self, Client, get):  # noqa
        client = Client.return_value
        r = Response({'status': 200})
        client.request.return_value = [
            r,
            json.dumps([{'type': 'bookmark', 'bookmark_id': 12345,
                         'title': 'Some bookmark',
                         'url': 'http://example.com/some-bookmark'}])
        ]

        user = UserFactory.create(
            read_later='instapaper',
            read_later_credentials=json.dumps({
                'oauth_token': 'token',
                'oauth_token_secret': 'token secret',
            }),
        )
        get.return_value = responses(304)
        feed = FeedFactory.create(category__user=user, user=user)

        get.return_value = responses(200, 'sw-all.xml')

        update_feed(feed.url)
        get.assert_called_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        entry_pk = Entry.objects.all()[0].pk
        url = reverse('feeds:item', args=[entry_pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, "Add to Instapaper")

        form = response.forms['read-later']
        response = form.submit()
        body = 'url=http%3A%2F%2Fsimonwillison.net%2F2010%2FMar%2F12%2Fre2%2F'
        client.request.assert_called_with(
            'https://www.instapaper.com/api/1/bookmarks/add',
            body=body,
            method='POST',
        )
        self.assertEqual(Entry.objects.get(pk=entry_pk).read_later_url,
                         'https://www.instapaper.com/read/12345')
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertNotContains(response, "Add to Instapaper")

    @patch('requests.get')
    @patch('requests.post')
    def test_add_to_readitlaterlist(self, post, get):
        user = UserFactory.create(
            read_later='readitlater',
            read_later_credentials=json.dumps({'username': 'foo',
                                               'password': 'bar'}),
        )

        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create(category__user=user, user=user)
        get.assert_called_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        url = reverse('feeds:item', args=[Entry.objects.all()[0].pk])
        response = self.app.get(url, user=force_bytes(user.username))
        self.assertContains(response, 'Add to Read it later')
        form = response.forms['read-later']
        response = form.submit()
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
        user = UserFactory.create()
        url = 'http://bruno.im/atom/tag/django-community/'
        get.return_value = responses(304)
        feed = FeedFactory.create(url=url, category__user=user, user=user)
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
    def test_subscribe_url(self, get):
        get.return_value = responses(304)

        user = UserFactory.create()
        c = CategoryFactory.create(user=user)

        url = reverse('feeds:subscribe')
        response = self.app.get(url, {'feeds': "http://bruno.im/atom/latest/"},
                                user=force_bytes(user.username))

        self.assertContains(response, 'value="http://bruno.im/atom/latest/"')
        form = response.forms['subscribe']

        response = form.submit()
        self.assertContains(response, 'This field is required.', 1)

        form['form-0-name'] = "Bruno's awesome blog"
        form['form-0-category'] = c.pk

        self.assertEqual(Feed.objects.count(), 0)
        response = form.submit().follow()
        self.assertEqual(Feed.objects.count(), 1)

        form['form-0-name'] = ""
        form['form-0-category'] = ""
        form['form-0-subscribe'] = False
        response = form.submit().follow()
        self.assertContains(response, '0 feeds have been added')

        form['form-0-name'] = 'Foo'
        form['form-0-category'] = c.pk
        form['form-0-subscribe'] = True
        response = form.submit()
        self.assertContains(response, "already subscribed")

        UniqueFeed.objects.create(url='http://example.com/feed',
                                  title='Awesome')
        response = self.app.get(
            url, {'feeds': ",".join(['http://bruno.im/atom/latest/',
                                     'http://example.com/feed'])})
        form = response.forms['subscribe']
        self.assertEqual(form['form-0-name'].value, 'Awesome')
        response = form.submit().follow()
        self.assertEqual(Feed.objects.count(), 2)

    def test_bookmarklet_no_feed(self):
        user = UserFactory.create()
        url = reverse('feeds:subscribe')
        response = self.app.get(url, {'url': 'http://isitbeeroclock.com/'},
                                user=force_bytes(user.username))
        self.assertContains(
            response, ('it looks like there are no feeds available on '
                       '<a href="http://isitbeeroclock.com/">'))

    @patch("requests.get")
    def test_relative_links(self, get):
        get.return_value = responses(200, path='brutasse.atom')

        user = UserFactory.create()
        FeedFactory.create(category__user=user, user=user,
                           url='https://github.com/brutasse.atom')
        entry = user.entries.all()[0]

        self.assertTrue('<a href="/brutasse"' in entry.subtitle)
        self.assertFalse('<a href="/brutasse"' in entry.content)
        self.assertTrue(
            '<a href="https://github.com/brutasse"' in entry.content)

        feed = Feed(url='http://standblog.org/blog/feed/rss2')
        e = Entry(feed=feed, subtitle=(
            ' <p><img alt=":-)" class="smiley"'
            'src="/dotclear2/themes/default/smilies/smile.png" /> . </p>'
        ))
        self.assertTrue(('src="http://standblog.org/dotclear2/themes/'
                         'default/smilies/smile.png"') in e.content)

    @patch('requests.get')
    def test_empty_subtitle(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        entry = EntryFactory(user=user, feed__category__user=user, subtitle='')
        url = reverse('feeds:item', args=[entry.pk])
        self.app.get(url, user=force_bytes(user.username))
