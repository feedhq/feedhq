# -*- coding: utf-8 -*-
import feedparser
import os
import random
import time

from django.test import TestCase
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from ..models import Category, Feed, Entry
from ..utils import FeedUpdater

feedparser.USER_AGENT = 'FeedHQ/dev +http://bitbucket.org/bruno/feedhq'
ROOT = os.path.abspath(os.path.dirname(__file__))


class FakeFeedParser(object):

    @staticmethod
    def parse(url, *args, **kwargs):
        if url.startswith('http://'):
            raise TypeError('Only local feeds in unit tests -- url was "%s"' %
                            url)
        url = os.path.join(ROOT, url)
        parsed = feedparser.parse(url)
        # Adding some HTTP sugar
        parsed['status'] = 200
        parsed['modified'] = time.localtime()
        parsed['etag'] = str(random.random())

        # Force some parameters here...
        if url.endswith('permanent.xml'):
            parsed.status = 301
            parsed.href = 'atom10.xml'

        if url.endswith('gone.xml'):
            parsed.status = 410

        if url.endswith('no-date.xml') and 'etag' in kwargs:
            parsed.entries = []
            parsed.status = 304

        if url.endswith('future.xml'):
            future_date = list(time.localtime())
            # Adding a year...
            future_date[0] = future_date[0] + 1
            if future_date[1] == 2 and future_date[2] == 29:
                future_date[2] = 28  # Fuck leap years
            parsed.entries[0].updated_parsed = future_date

        if url.endswith('no-status.xml'):
            parsed = {
                'feed': {},
                'bozo': 1,
                'bozo_exception': "Name or service not known",
                'entries': [],
            }

        if url.endswith('no-link.xml'):
            parsed.entries[0]['link'] = None
        return parsed


def fake_update(url):
    updater = FeedUpdater(url, feedparser=FakeFeedParser)
    updater.update()


class BaseTests(TestCase):
    """Tests that do not require specific setup"""
    def test_welcome_page(self):
        self.user = User.objects.create_user('testuser',
                                             'foo@example.com',
                                             'pass')
        self.client.login(username='testuser', password='pass')
        url = reverse('feeds:home')
        response = self.client.get(url)
        self.assertContains(response, 'Getting started')
        cat = self.user.categories.create(name='Foo', slug='foo')

        feed = Feed(name='yo', url='http://example.com/feed', category=cat)
        feed.skip_post_save = True
        feed.save()

        response = self.client.get(url)
        self.assertNotContains(response, 'Getting started')


class TestFeeds(TestCase):

    def setUp(self):
        """Main stuff we need for testing the app - this is mainly for signed
        in users."""
        # We'll need a user...
        self.user = User.objects.create_user('testuser',
                                             'foo@example.com',
                                             'pass')
        # ... a category...
        cat = Category(name='Cat', slug='cat', user=self.user,
                       delete_after='never')
        cat.save()
        self.cat = cat

        # ... and a feed.
        feed = Feed(name='Test Feed', category=self.cat, url='sw-all.xml',
                    delete_after='never')
        feed.save()
        self.feed = feed

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

    def test_feed_model(self):
        """Behaviour of the ``Feed`` model"""
        feed = Feed(name='RSS test', url='rss20.xml', category=self.cat,
                    muted=False)
        feed.save()
        self.cat.delete_after = 'never'
        self.cat.save()

        feed_from_db = Feed.objects.get(pk=feed.id)

        # __unicode__
        self.assertEqual('%s' % feed_from_db, 'RSS test')

        # get_absolute_url()
        self.assertEqual('/feed/%s/' % feed.id, feed.get_absolute_url())

        # update()
        fake_update(feed.url)
        feed = Feed.objects.get(pk=feed.id)
        self.assertEqual(feed.title, 'Sample Feed')
        self.assertEqual(feed.link, 'http://example.org/')
        self.assertEqual(feed.entries.count(), 1)
        self.assertEqual(feed.entries.all()[0].title, 'First item title')
        # Testing the use of etags/modified headers
        fake_update(feed.url)
        self.assertEqual(feed.entries.count(), 1)

        # remove_old_entries won't run if delete_after is never
        self.cat.delete_after = 'never'
        self.cat.save()
        fake_update(feed.url)

    def test_entry_model(self):
        fake_update(self.feed.url)
        title = 'RE2: a principled approach to regular expression matching'
        entry = Entry.objects.get(title=title)

        # __unicode__
        self.assertEqual('%s' % entry, title)

        # get_link()
        self.assertEqual(entry.get_link(), entry.link)
        # Setting permalink
        entry.permalink = 'http://example.com/some-url'
        self.assertEqual(entry.get_link(), entry.permalink)

    def test_permanent_redirects(self):
        """Updating the feed if there's a permanent redirect"""
        feed = Feed(name='Permanent', category=self.cat,
                    url='permanent.xml')
        feed.save()
        fake_update(feed.url)
        feed = Feed.objects.get(pk=feed.id)
        self.assertEqual(feed.url, 'atom10.xml')

    def test_content_handling(self):
        """The content section overrides the subtitle section"""
        feed = Feed(name='Content', category=self.cat,
                    url='atom10.xml')
        feed.save()
        fake_update(feed.url)
        entry = Entry.objects.get()
        self.assertTrue('Watch out for <span> nasty tricks' in entry.subtitle)

    def test_gone(self):
        """Muting the feed if the status code is 410"""
        feed = Feed(name='Gone', category=self.cat, url='gone.xml')
        feed.save()
        fake_update(feed.url)
        feed = Feed.objects.get(pk=feed.id)
        self.assertTrue(feed.muted)

    def test_no_date_and_304(self):
        """If the feed does not have a date, we'll have to find one.
        Also, since we update it twice, the 2nd time it's a 304 response."""
        feed = Feed(name='Django Community', category=self.cat,
                    url='no-date.xml')
        feed.save()

        # Update the feed twice and make sure we don't index the content twice
        fake_update(feed.url)
        feed1 = Feed.objects.get(pk=feed.id)
        count1 = feed1.entries.count()

        fake_update(feed1.url)
        feed2 = Feed.objects.get(pk=feed1.id)
        count2 = feed2.entries.count()

        self.assertEqual(count1, count2)

    def test_no_status(self):
        self.feed.url = 'no-status.xml'
        self.feed.save()
        fake_update(self.feed.url)
        self.assertEqual(Entry.objects.count(), 0)

    def test_auto_mute_feed(self):
        """Auto-muting feeds with no status for too long"""
        self.feed.url = 'no-status.xml'
        self.feed.save()
        fake_update(self.feed.url)
        self.assertEqual(Entry.objects.count(), 0)
        self.assertEqual(Feed.objects.get(url=self.feed.url).failed_attempts, 1)
        for i in range(20):
            fake_update(self.feed.url)
        feed = Feed.objects.get(url=self.feed.url)
        self.assertEqual(feed.failed_attempts, 20)
        self.assertTrue(feed.muted)

    def test_no_link(self):
        self.feed.url = 'rss20.xml'
        self.feed.save()
        fake_update(self.feed.url)
        self.assertEqual(Entry.objects.count(), 1)

        self.feed.url = 'no-link.xml'
        self.feed.save()
        fake_update(self.feed.url)
        self.assertEqual(Entry.objects.count(), 1)

    def test_multiple_objects(self):
        """Duplicates are removed at the next update"""
        fake_update(self.feed.url)
        entry = self.feed.entries.all()[0]
        entry.id = None
        entry.save()
        entry.id = None
        entry.save()
        self.assertEqual(self.feed.entries.count(), 32)
        fake_update(self.feed.url)
        self.assertEqual(self.feed.entries.count(), 30)

    def test_screenscraping(self):
        self.feed.screenscraping = 'bob'
        self.feed.save()
        fake_update(self.feed.url)
        # FIXME mock something

    def test_future_date(self):
        self.feed.url = 'future.xml'
        self.feed.save()
        fake_update(self.feed.url)
        self.assertEqual(self.feed.entries.count(), 1)

    def test_entry_model_behaviour(self):
        """Behaviour of the `Entry` model"""
        entry = Entry(feed=self.feed, title='My title', user=self.user,
                      date=timezone.now())
        entry.save()

        # __unicode__
        self.assertEqual('%s' % entry, 'My title')

        # get_absolute_url()
        self.assertEqual('/entries/%s/' % entry.id, entry.get_absolute_url())

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

        self.assertContains(
            response,
            '<a href="%sunread/">Show only unread</a>' % self.feed.get_absolute_url(),
        )

    def test_only_unread(self):
        url = reverse('feeds:unread_category', args=['cat'])
        response = self.client.get(url)

        self.assertContains(response, 'Cat')
        self.assertContains(response, 'Show all')

    def test_add_category(self):
        url = reverse('feeds:add_category')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        bad_data = {'name': ''}
        response = self.client.post(url, bad_data)
        self.assertContains(response, 'errorlist')

        data = {'name': 'New Name', 'color': 'red', 'delete_after': '1day'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/category/new-name/' in response['Location'])

        # Adding a category with the same name. The slug will be different
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/category/new-name-/' in response['Location'])

        # Now we add a category named 'add', which is a conflicting URL
        data = {'name': 'Add', 'color': 'red', 'delete_after': '1day'}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/category/add-/' in response['Location'])

    def test_delete_category(self):
        url = reverse('feeds:delete_category', args=['cat'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 302)

    def test_edit_category(self):
        url = reverse('feeds:edit_category', args=['cat'])
        response = self.client.get(url)
        self.assertContains(response, 'Edit Cat')

        data = {'name': 'New Name', 'color': 'blue', 'delete_after': '2days'}
        response = self.client.post(url, data)
        self.assertContains(response,
                            'New Name has been successfully updated')

    def test_add_feed(self):
        url = reverse('feeds:add_feed')
        response = self.client.get(url)
        self.assertContains(response, 'Add a feed')

        bad_data = {'name': 'Lulz'}  # there is no URL / category
        response = self.client.post(url, bad_data)
        self.assertContains(response, 'errorlist')

        data = {'name': 'Bobby', 'url': 'http://example.com/feed.xml',
                'category': self.cat.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/category/cat/' in response['Location'])

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

        # Now overrides
        data['override'] = True
        data['delete_after'] = '1day'
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, 'New Name has been successfully updated')
        feed = Feed.objects.get(pk=self.feed.id)
        self.assertTrue(feed.override)

        # Disabling overrides
        data['override'] = False
        response = self.client.post(url, data, follow=True)
        self.assertContains(response, 'New Name has been successfully updated')
        feed = Feed.objects.get(pk=self.feed.id)
        self.assertFalse(feed.override)
        self.assertEqual(feed.delete_after, '')

    def test_delete_feed(self):
        url = reverse('feeds:delete_feed', args=[self.feed.id])
        response = self.client.get(url)
        self.assertContains(response, 'Delete')
        self.assertContains(response, self.feed.name)

        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 302)
        # Redirects to home so useless to test

    def test_invalid_page(self):
        # We need more than 25 entries
        fake_update(self.feed.url)
        url = reverse('feeds:home', args=[12000])  # that page doesn't exist
        response = self.client.get(url)
        self.assertContains(response, '<a href="/">1</a>')

    def _test_entry(self, from_url):
        self.assertEqual(self.client.get(from_url).status_code, 200)

        e = Entry.objects.get(title="jacobian's django-deployment-workshop")
        url = reverse('feeds:item', args=[e.pk])
        response = self.client.get(url)
        self.assertContains(response, "jacobian's django-deployment-workshop")
        self.assertContains(response, '<a href="%s">⇠ Back</a>' % from_url)

    def test_entry(self):
        fake_update(self.feed.url)

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

    def test_last_entry(self):
        fake_update(self.feed.url)

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
        self.assertContains(response, 'Show images')
        response = self.client.post(url, {'action': 'images'})
        self.assertContains(response, 'Always show images')
        response = self.client.post(url, {'action': 'images_always'})
        self.assertContains(response, 'Hide images')
        response = self.client.post(url, {'action': 'images_never'})
        self.assertNotContains(response, 'Hide images')

    def test_opml_import(self):
        url = reverse('feeds:import_feeds')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        with open(os.path.join(ROOT, 'sample.opml'), 'r') as opml_file:
            data = {'file': opml_file}
            response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, '2 feeds have been imported')
        self.assertEqual(Category.objects.filter(name='Imported').count(), 1)

        # Re-import
        with open(os.path.join(ROOT, 'sample.opml'), 'r') as opml_file:
            data = {'file': opml_file}
            response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, '0 feeds have been imported')

    def test_categories_in_opml(self):
        url = reverse('feeds:import_feeds')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        with open(os.path.join(ROOT, 'categories.opml'), 'r') as opml_file:
            data = {'file': opml_file}
            response = self.client.post(url, data, follow=True)
        self.assertEqual(len(response.redirect_chain), 1)
        self.assertContains(response, '15 feeds have been imported')
        self.assertEqual(self.user.categories.count(), 7)

    def test_dashboard(self):
        url = reverse('feeds:dashboard')
        response = self.client.get(url)
        self.assertContains(response, 'Dashboard')
