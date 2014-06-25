# -*- coding: utf-8 -*-
import feedparser
import json

from datetime import timedelta

from django.core.urlresolvers import reverse
from django.utils import timezone
from django_push.subscriber.signals import updated
from mock import patch
from rache import schedule_job

from feedhq import es
from feedhq.feeds.models import Category, Feed, Entry, UniqueFeed
from feedhq.feeds.tasks import update_feed
from feedhq.feeds.templatetags.feeds_tags import smart_date
from feedhq.feeds.utils import USER_AGENT
from feedhq.profiles.models import User
from feedhq.utils import get_redis_connection
from feedhq.wsgi import application  # noqa

from .factories import UserFactory, CategoryFactory, FeedFactory, EntryFactory
from . import data_file, responses, patch_job, WebTest


class WebBaseTests(WebTest):
    @patch('requests.get')
    def test_welcome_page(self, get):
        get.return_value = responses(304)

        self.user = User.objects.create_user('testuser',
                                             'foo@example.com',
                                             'pass')
        user = UserFactory.create()
        url = reverse('feeds:home')
        response = self.app.get(url, user=user)
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
                                user=user)
        self.assertContains(response, 'Home')
        self.assertContains(response, user.username)

    def test_unauth_homepage(self):
        """The home page from a logged-out user"""
        response = self.app.get(reverse('feeds:home'))
        self.assertContains(response, 'Sign in')  # login required

    def test_paginator(self):
        user = UserFactory.create()
        response = self.app.get(reverse('feeds:home', args=[5]),
                                user=user)
        self.assertContains(response, 'Home')

    def test_category(self):
        user = UserFactory.create()
        CategoryFactory.create(user=user, name=u'Cat yo')
        url = reverse('feeds:category', args=['cat-yo'])
        response = self.app.get(url, user=user)
        self.assertContains(response, 'Cat yo')

    @patch("requests.get")
    def test_only_unread(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        FeedFactory.create(category=category, user=user)
        url = reverse('feeds:unread_category', args=[category.slug])
        response = self.app.get(url, user=user)

        self.assertContains(response, category.name)
        self.assertContains(response, 'all <span class="ct">')

    def test_add_category(self):
        user = UserFactory.create()
        url = reverse('feeds:add_category')
        response = self.app.get(url, user=user)

        form = response.forms['category']
        response = form.submit()
        self.assertFormError(response, 'form', 'name',
                             ['This field is required.'])

        form['name'] = 'New Name' * 50
        form['color'] = 'red'
        response = form.submit()
        self.assertFormError(response, 'form', 'name',
                             'This name is too long. Please shorten it to 50 '
                             'characters or less.')
        form['name'] = 'New Name'
        response = form.submit()
        self.assertRedirects(response, '/manage/')

        # Re-submitting the same name fails
        response = form.submit()
        self.assertFormError(response, 'form', 'name',
                             ['A category with this name already exists.'])

        # Adding a category with a name generating the same slug.
        # The slug will be different
        form['name'] = 'New  Name'
        response = form.submit()
        user.categories.get(slug='new-name-1')
        self.assertRedirects(response, '/manage/')

        # Now we add a category named 'add', which is a conflicting URL
        form['name'] = 'add'
        response = form.submit()
        user.categories.get(slug='add-1')
        self.assertRedirects(response, '/manage/')

        # Add a category with non-ASCII names, slugify should cope
        form['name'] = u'北京'
        response = form.submit()
        user.categories.get(slug='unknown')
        self.assertRedirects(response, '/manage/')
        form['name'] = u'北'
        response = form.submit()
        user.categories.get(slug='unknown-1')
        self.assertRedirects(response, '/manage/')
        form['name'] = u'京'
        response = form.submit()
        user.categories.get(slug='unknown-2')
        self.assertRedirects(response, '/manage/')

    def test_delete_category(self):
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        url = reverse('feeds:delete_category', args=[category.slug])
        response = self.app.get(url, user=user)
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
        response = self.app.get(url, user=user)

        expected = (
            '<a href="{0}unread/">unread <span class="ct">0</span></a>'
        ).format(feed.get_absolute_url())
        self.assertContains(response, expected)

    def test_edit_category(self):
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        url = reverse('feeds:edit_category', args=[category.slug])
        response = self.app.get(url, user=user)
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
        response = self.app.get(url, user=user)
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
        redis = get_redis_connection()
        redis.set(cache_key, user.pk)
        response = form.submit()
        self.assertFormError(response, 'form', 'url', [
            "This action can only be done one at a time.",
        ])
        redis.delete(cache_key)

        get.return_value = responses(200, 'brutasse.atom')
        response = form.submit()
        self.assertRedirects(response, '/manage/')
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

        get.side_effect = ValueError
        user.feeds.all().delete()
        response = form.submit()
        self.assertFormError(response, 'form', 'url',
                             ['Error fetching the feed.'])

    def test_feed_url_validation(self):
        user = UserFactory.create()
        category = CategoryFactory.create(user=user)
        url = reverse('feeds:add_feed')
        response = self.app.get(url, user=user)

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
        response = self.app.get(url, user=user)
        self.assertContains(response, feed.name)

        form = response.forms['feed']

        form['name'] = 'New Name'
        form['url'] = 'http://example.com/newfeed.xml'
        get.return_value = responses(200, 'brutasse.atom')
        response = form.submit().follow()
        self.assertContains(response, 'New Name has been successfully updated')

        cat = CategoryFactory.create(user=user)
        response = self.app.get(url, user=user)
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
        response = self.app.get(url, user=user)
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
        response = self.app.get(url, user=user)
        self.assertContains(response, '<a href="/" class="current">')

    # This is called by other tests
    def _test_entry(self, from_url, user):
        self.assertEqual(self.app.get(
            from_url, user=user).status_code, 200)

        e = es.manager.user(user).filter(
            query='title:"jacobian\'s django-deployment-workshop"',
        ).fetch()['hits'][0]
        url = reverse('feeds:item', args=[e.pk])
        response = self.app.get(url, user=user)
        self.assertContains(response, "jacobian's django-deployment-workshop")

    @patch('requests.get')
    def test_entry(self, get):
        user = UserFactory.create(ttl=99999)
        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create(category__user=user, user=user)

        url = reverse('feeds:home')
        self._test_entry(url, user)

        url = reverse('feeds:unread')
        self._test_entry(url, user)

        url = reverse('feeds:stars')
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
    def test_custom_ordering(self, get):
        user = UserFactory.create()
        get.return_value = responses(200, 'sw-all.xml')
        FeedFactory.create(user=user, category__user=user)

        url = reverse('feeds:unread')
        response = self.app.get(url, user=user)
        object_list = response.context['entries']['object_list']
        first_title = object_list[0].title
        last_title = object_list[-1].title

        user.oldest_first = True
        user.save()
        response = self.app.get(url, user=user)

        object_list = response.context['entries']['object_list']

        self.assertEqual(object_list[0].title, last_title)
        self.assertEqual(object_list[-1].title, first_title)

    @patch('requests.get')
    def test_last_entry(self, get):
        user = UserFactory.create()
        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create(category__user=user, user=user)

        with self.assertNumQueries(1):
            update_feed(feed.url)

        last_item = es.manager.user(user).order_by(
            'timestamp').fetch()['hits'][0]
        url = reverse('feeds:item', args=[last_item.pk])
        response = self.app.get(url, user=user)
        self.assertNotContains(response, 'Next →')

    def test_not_mocked(self):
        with self.assertRaises(ValueError):
            FeedFactory.create()

    def test_item_404(self):
        user = UserFactory.create()
        url = reverse('feeds:item', args=[99999])
        self.app.get(url, user=user, status=404)

    @patch("requests.get")
    def test_img(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        feed = FeedFactory.create(category__user=user, url='http://exmpl.com',
                                  user=user)
        entry = EntryFactory.create(
            feed=feed,
            title="Random title",
            subtitle='<img src="/favicon.png">',
            link='http://example.com',
            date=timezone.now(),
            user=user,
        )
        url = reverse('feeds:item', args=[entry.pk])
        response = self.app.get(url, user=user)
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

    @patch("requests.get")
    def test_actions(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        feed = FeedFactory.create(category__user=user, url='http://exmpl.com',
                                  user=user)
        entry = EntryFactory.create(
            feed=feed,
            title="Random title",
            subtitle='Foo bar content',
            link='http://example.com',
            date=timezone.now(),
            user=user,
        )
        url = reverse('feeds:item', args=[entry.pk])
        response = self.app.get(url, user=user)
        token = response.forms['unread'].fields['csrfmiddlewaretoken'][0].value
        response = self.app.post(url, {'action': 'invalid',
                                       'csrfmiddlewaretoken': token},
                                 user=user)

        form = response.forms['star']
        response = form.submit()
        self.assertTrue(es.manager.user(user).fetch()['hits'][0].starred)
        form = response.forms['star']
        response = form.submit()
        [entry] = es.manager.user(user).fetch()['hits']
        self.assertFalse(entry.starred)

        user.oldest_first = True
        user.save(update_fields=['oldest_first'])

        form = response.forms['unread']
        response = form.submit()

        [entry] = es.manager.user(user).fetch()['hits']
        self.assertFalse(entry.read)

    @patch('requests.get')
    def test_opml_import(self, get):
        user = UserFactory.create()
        url = reverse('feeds:import_feeds')
        response = self.app.get(url, user=user)

        get.return_value = responses(304)
        form = response.forms['import']

        with open(data_file('sample.opml'), 'rb') as opml_file:
            form['file'] = 'sample.opml', opml_file.read()
        response = form.submit().follow()

        self.assertContains(response, '2 feeds have been imported')

        # Re-import
        with open(data_file('sample.opml'), 'rb') as opml_file:
            form['file'] = 'sample.opml', opml_file.read()
        response = form.submit().follow()
        self.assertContains(response, '0 feeds have been imported')

        # Import an invalid thing
        form['file'] = 'invalid', b"foobar"
        response = form.submit()
        self.assertFormError(response, 'form', 'file', [
            "This file doesn't seem to be a valid OPML file."
        ])

        # Empty file
        form['file'] = 'name', b""
        response = form.submit()
        self.assertFormError(response, 'form', 'file', [
            "The submitted file is empty."
        ])

    @patch('requests.get')
    def test_greader_opml_import(self, get):
        user = UserFactory.create()
        url = reverse('feeds:import_feeds')
        response = self.app.get(url, user=user)

        get.return_value = responses(304)
        form = response.forms['import']

        with open(data_file('google-reader-subscriptions.xml'),
                  'rb') as opml_file:
            form['file'] = 'sample.opml', opml_file.read()
        response = form.submit().follow()

        self.assertContains(response, '1 feed has been imported')
        self.assertEqual(Category.objects.count(), 0)

    @patch('requests.get')
    def test_categories_in_opml(self, get):
        user = UserFactory.create()
        url = reverse('feeds:import_feeds')
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 200)

        get.return_value = responses(304)

        form = response.forms["import"]

        with open(data_file('categories.opml'), 'rb') as opml_file:
            form['file'] = 'categories.opml', opml_file.read()

        response = form.submit().follow()
        self.assertContains(response, '20 feeds have been imported')
        self.assertEqual(user.categories.count(), 6)
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
        response = self.app.get(url, user=user)
        self.assertContains(response, 'Dashboard')

    @patch('requests.get')
    def test_unread_dashboard(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        url = reverse('feeds:unread_dashboard')
        FeedFactory.create(category=None, user=user)
        for i in range(5):
            FeedFactory.create(category__user=user, user=user)
        response = self.app.get(url, user=user)
        self.assertContains(response, 'Dashboard')

    @patch('requests.get')
    def test_unread_count(self, get):
        """Unread feed count everywhere"""
        user = UserFactory.create(ttl=99999)
        url = reverse('profile')
        response = self.app.get(url, user=user)
        self.assertContains(
            response,
            '<a class="unread" title="Unread entries" href="/unread/">0</a>'
        )

        get.return_value = responses(200, 'sw-all.xml')
        FeedFactory.create(category__user=user, user=user)

        response = self.app.get(url, user=user)
        self.assertContains(
            response,
            '<a class="unread" title="Unread entries" href="/unread/">30</a>'
        )

    @patch('requests.get')
    def test_mark_as_read(self, get):
        get.return_value = responses(304)
        user = UserFactory.create(ttl=99999)
        feed = FeedFactory.create(category__user=user, user=user)
        url = reverse('feeds:unread')
        response = self.app.get(url, user=user)
        self.assertNotContains(response, '"Mark all as read"')

        get.return_value = responses(200, 'sw-all.xml')
        update_feed(feed.url)

        response = self.app.get(url, user=user)
        self.assertContains(response, '"Mark all as read"')

        form = response.forms['read-all']
        response = form.submit()
        self.assertRedirects(response, url)
        response = response.follow()
        self.assertContains(response, '30 entries have been marked as read')

        counts = self.counts(user, read={'read': True},
                             unread={'read': False})
        unread = counts['unread']
        read = counts['read']
        self.assertEqual(unread, 0)
        self.assertEqual(read, 30)

        form = response.forms['undo']
        response = form.submit()
        self.assertRedirects(response, url)
        response = response.follow()
        self.assertContains(response, "30 entries have been marked as unread")

        counts = self.counts(user, read={'read': True},
                             unread={'read': False})
        unread = counts['unread']
        read = counts['read']
        self.assertEqual(unread, 30)
        self.assertEqual(read, 0)

        form = response.forms['read-page']
        some_entries = es.manager.user(user).only('_id').fetch(per_page=5)
        some_entries = [e.pk for e in some_entries['hits']]
        form['entries'] = json.dumps(list(some_entries))
        response = form.submit()
        self.assertRedirects(response, url)
        response = response.follow()
        self.assertContains(response, "5 entries have been marked as read")

    @patch('requests.get')
    def test_promote_html_content_type(self, get):
        get.return_value = responses(200, 'content-description.xml')
        user = UserFactory.create(ttl=99999)
        FeedFactory.create(user=user)
        content = es.manager.user(user).fetch(
            per_page=1, annotate=user)['hits'][0].content
        self.assertEqual(len(content.split('F&#233;vrier 1953')), 2)

    @patch('requests.get')
    @patch('requests.post')
    def test_add_to_readability(self, post, get):  # noqa
        post.return_value = responses(202, headers={
            'location': 'https://www.readability.com/api/rest/v1/bookmarks/19',
        })

        user = UserFactory.create(
            read_later='readability',
            read_later_credentials=json.dumps({
                'oauth_token': 'token',
                'oauth_token_secret': 'token secret',
            }),
        )

        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create(category__user=user, user=user)
        get.assert_called_once_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        get.reset_mock()
        get.return_value = responses(200, data=json.dumps(
            {'article': {'id': 'foo'}}))

        entry_pk = es.manager.user(user).fetch()['hits'][0].pk
        url = reverse('feeds:item', args=[entry_pk])
        response = self.app.get(url, user=user)
        self.assertContains(response, "Add to Readability")

        form = response.forms['read-later']
        response = form.submit()
        self.assertEqual(len(post.call_args_list), 1)
        self.assertEqual(len(get.call_args_list), 1)
        args, kwargs = post.call_args
        self.assertEqual(
            args, ('https://www.readability.com/api/rest/v1/bookmarks',))
        self.assertEqual(kwargs['data'], {
            'url': 'http://simonwillison.net/2010/Mar/12/re2/'})
        args, kwargs = get.call_args
        self.assertEqual(
            args, ('https://www.readability.com/api/rest/v1/bookmarks/19',))
        entry = es.entry(user, entry_pk)
        self.assertEqual(entry.read_later_url,
                         'https://www.readability.com/articles/foo')
        response = self.app.get(url, user=user)
        self.assertNotContains(response, "Add to Instapaper")

    @patch("requests.get")
    @patch('requests.post')
    def test_add_to_instapaper(self, post, get):  # noqa
        post.return_value = responses(200, data=json.dumps([{
            'type': 'bookmark', 'bookmark_id': 12345,
            'title': 'Some bookmark',
            'url': 'http://example.com/some-bookmark',
        }]))

        user = UserFactory.create(
            read_later='instapaper',
            read_later_credentials=json.dumps({
                'oauth_token': 'token',
                'oauth_token_secret': 'token secret',
            }),
        )
        get.return_value = responses(304)
        feed = FeedFactory.create(category__user=user, user=user)

        get.reset_mock()
        get.return_value = responses(200, 'sw-all.xml')

        update_feed(feed.url)
        get.assert_called_once_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        entry_pk = es.manager.user(user).fetch()['hits'][0].pk
        url = reverse('feeds:item', args=[entry_pk])
        response = self.app.get(url, user=user)
        self.assertContains(response, "Add to Instapaper")

        form = response.forms['read-later']
        response = form.submit()
        self.assertEqual(len(post.call_args_list), 1)
        args, kwargs = post.call_args
        self.assertEqual(args,
                         ('https://www.instapaper.com/api/1/bookmarks/add',))
        self.assertEqual(kwargs['data'],
                         {'url': 'http://simonwillison.net/2010/Mar/12/re2/'})
        entry = es.entry(user, entry_pk)
        self.assertEqual(entry.read_later_url,
                         'https://www.instapaper.com/read/12345')
        response = self.app.get(url, user=user)
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

        entry_pk = es.manager.user(user).fetch()['hits'][0].pk
        url = reverse('feeds:item', args=[entry_pk])
        response = self.app.get(url, user=user)
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
        user = UserFactory.create(ttl=99999)
        url = 'http://bruno.im/atom/tag/django-community/'
        get.return_value = responses(304)
        feed = FeedFactory.create(url=url, category__user=user, user=user)
        get.assert_called_with(
            url, headers={'User-Agent': USER_AGENT % '1 subscriber',
                          'Accept': feedparser.ACCEPT_HEADER},
            timeout=10)

        self.assertEqual(feed.entries.count(), 0)
        path = data_file('bruno.im.atom')
        with open(path, 'r') as f:
            data = f.read()
        updated.send(sender=None, notification=data, request=None, links=None)

        entries = self.counts(user, feed={'feed': feed.pk})['feed']
        self.assertEqual(entries, 5)

        # Check content handling
        entries = es.manager.user(user).filter(
            feed=feed.pk).fetch()['hits']

        for entry in entries:
            self.assertTrue(len(entry.subtitle) > 2400)

        # Check date handling
        eleven = es.manager.user(user).filter(
            feed=feed.pk,
            timestamp__gt='2010-12-31',
            timestamp__lt='2012-01-01'
        ).fetch()
        eleven = len(eleven['hits'])
        twelve = es.manager.user(user).filter(
            feed=feed.pk,
            timestamp__gt='2011-12-31',
            timestamp__lt='2013-01-01'
        ).fetch()
        twelve = len(twelve['hits'])
        self.assertEqual(eleven, 3)
        self.assertEqual(twelve, 2)

    @patch('requests.get')
    def test_missing_links(self, get):
        path = data_file('no-rel.atom')
        with open(path, 'r') as f:
            data = f.read()
        updated.send(sender=None, notification=data, request=None, links=None)

    @patch('requests.get')
    def test_link_headers(self, get):
        user = UserFactory.create(ttl=99999)
        url = 'foo'
        get.return_value = responses(304)
        FeedFactory.create(url=url, category__user=user, user=user)

        path = data_file('no-rel.atom')
        with open(path, 'r') as f:
            data = f.read()
        updated.send(sender=None, notification=data, request=None,
                     links=[{'url': 'foo', 'rel': 'self'}])
        self.assertEqual(es.client.count(es.user_alias(user.pk),
                                         doc_type='entries')['count'], 1)

    @patch('requests.get')
    def test_subscribe_url(self, get):
        get.return_value = responses(304)

        user = UserFactory.create()
        c = CategoryFactory.create(user=user)

        url = reverse('feeds:subscribe')
        response = self.app.get(url, {'feeds': "http://bruno.im/atom/latest/"},
                                user=user)

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

        u = UniqueFeed.objects.create(url='http://example.com/feed')
        u.schedule()
        patch_job(u.url, title='Awesome')
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
                                user=user)
        self.assertContains(
            response, ('it looks like there are no feeds available on '
                       '<a href="http://isitbeeroclock.com/">'))

    @patch("requests.get")
    def test_relative_links(self, get):
        get.return_value = responses(200, path='brutasse.atom')

        user = UserFactory.create(ttl=99999)
        FeedFactory.create(category__user=user, user=user,
                           url='https://github.com/brutasse.atom')
        entry = es.manager.user(user).fetch(annotate=user)['hits'][0]

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
        entry = EntryFactory.create(user=user, feed__user=user,
                                    feed__category__user=user, subtitle='')
        url = reverse('feeds:item', args=[entry.pk])
        self.app.get(url, user=user)

    def test_smart_date(self):
        now = timezone.now()
        self.assertEqual(len(smart_date(now)), 5)

        if now.day != 1 and now.month != 1:  # Can't test this on Jan 1st :)
            now = now - timedelta(days=1)
            self.assertEqual(len(smart_date(now)), 6)

        now = now - timedelta(days=366)
        self.assertEqual(len(smart_date(now)), 12)

    @patch('requests.get')
    def test_manage_feed(self, get):
        get.return_value = responses(304)
        user = UserFactory.create()
        url = reverse('feeds:manage')
        response = self.app.get(url, user=user)
        self.assertContains(response, 'Manage feeds')

        FeedFactory.create(user=user, category=None)
        FeedFactory.create(user=user, category=None)
        FeedFactory.create(user=user, category=None)
        unique = UniqueFeed.objects.all()[0]
        schedule_job(unique.url, schedule_in=0, backoff_factor=10,
                     error=UniqueFeed.NOT_A_FEED,
                     connection=get_redis_connection())

        response = self.app.get(url, user=user)
        self.assertContains(response, 'Not a valid RSS/Atom feed')

        schedule_job(unique.url, schedule_in=0, error='blah',
                     connection=get_redis_connection())
        response = self.app.get(url, user=user)
        self.assertContains(response, 'Error')

        unique.muted = True
        unique.save()
        response = self.app.get(url, user=user)
        self.assertContains(response, 'Error')

    def test_health(self):
        url = reverse('health')
        with self.assertNumQueries(4):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        expected = {
            'feeds': {'total': 0, 'unique': 0},
            'queues': {},
            'users': {'active': 0, 'total': 0},
        }
        self.assertEqual(json.loads(response.content.decode('utf-8')),
                         expected)

        with self.settings(HEALTH_SECRET='foo'):
            response = self.client.get(url, HTTP_X_TOKEN='bar')
            self.assertEqual(response.status_code, 403)

            response = self.client.get(url, HTTP_X_TOKEN='foo')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.content.decode('utf-8')),
                             expected)
