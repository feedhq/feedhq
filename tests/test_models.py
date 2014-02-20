# -*- coding: utf-8 -*-
from datetime import timedelta
from django.utils import timezone
from mock import patch
from rache import job_details, schedule_job

from feedhq.feeds.models import (Category, Feed, UniqueFeed, Entry, Favicon,
                                 UniqueFeedManager)
from feedhq.feeds.tasks import update_feed
from feedhq.utils import get_redis_connection

from .factories import CategoryFactory, FeedFactory
from . import responses, ClearRedisTestCase


class ModelTests(ClearRedisTestCase):
    def test_category_model(self):
        """Behaviour of the ``Category`` model"""
        cat = CategoryFactory.create(name='New Cat', slug='new-cat')

        cat_from_db = Category.objects.get(pk=cat.id)

        # __unicode__
        self.assertEqual('%s' % cat_from_db, 'New Cat')

        # get_absolute_url()
        self.assertEqual('/category/new-cat/', cat_from_db.get_absolute_url())

    @patch('requests.get')
    def test_feed_model(self, get):
        """Behaviour of the ``Feed`` model"""
        get.return_value = responses(200, 'rss20.xml')
        feed = FeedFactory.create(name='RSS test', url='rss20.xml')
        feed.save()

        feed_from_db = Feed.objects.get(pk=feed.id)

        # __unicode__
        self.assertEqual('%s' % feed_from_db, 'RSS test')

        # get_absolute_url()
        self.assertEqual('/feed/%s/' % feed.id, feed.get_absolute_url())

        # update()
        update_feed(feed.url)

        data = job_details(feed.url, connection=get_redis_connection())

        self.assertEqual(data['title'], 'Sample Feed')
        self.assertEqual(data['link'], 'http://example.org/')

        feed = Feed.objects.get(pk=feed.id)
        self.assertEqual(feed.entries.count(), 1)
        self.assertEqual(feed.entries.all()[0].title, 'First item title')

        self.assertEqual(feed.favicon_img(), '')
        feed.favicon = 'fav.png'
        self.assertEqual(feed.favicon_img(),
                         '<img src="/media/fav.png" width="16" height="16" />')

    @patch('requests.get')
    def test_entry_model(self, get):
        get.return_value = responses(200, 'sw-all.xml')
        feed = FeedFactory.create()
        update_feed(feed.url)
        title = 'RE2: a principled approach to regular expression matching'
        entry = Entry.objects.get(title=title)

        # __unicode__
        self.assertEqual('%s' % entry, title)

        entry.title = ''
        self.assertEqual(entry.sanitized_title(), '(No title)')

        entry.title = 'Foo'
        entry.link = 'http://example.com/foo'
        self.assertEqual(entry.tweet(),
                         u'Foo — http://example.com/foo')

    @patch('requests.get')
    def test_uniquefeed_model(self, get):
        get.return_value = responses(304)
        FeedFactory.create(url='http://example.com/' + 'foo/' * 200)
        unique = UniqueFeed.objects.get()
        self.assertEqual(len(unique.truncated_url()), 50)

        unique.delete()

        FeedFactory.create(url='http://example.com/foo/')
        unique = UniqueFeed.objects.get()
        self.assertEqual(len(unique.truncated_url()), len(unique.url))

        unique = UniqueFeed(url='http://foo.com')
        self.assertEqual('%s' % unique, 'http://foo.com')

        self.assertIs(UniqueFeedManager.entry_data({}, None), None)

        unique.schedule()
        details = unique.job_details
        at = details.pop('schedule_at')
        details.pop('last_update')
        self.assertEqual(details, {
            u"backoff_factor": 1,
            u"subscribers": 1,
            u"id": "http://foo.com",
        })
        details['schedule_at'] = at
        self.assertEqual(unique.job_details['id'], "http://foo.com")

        self.assertTrue(unique.scheduler_data.startswith("{\n"))

        self.assertTrue(unique.next_update > timezone.now())
        self.assertTrue(unique.next_update <
                        timezone.now() + timedelta(seconds=60 * 61))

        schedule_job(unique.url, title='Lol', schedule_in=0)
        del unique._job_details
        details = unique.job_details
        details.pop('schedule_at')
        details.pop('last_update')
        self.assertEqual(details, {
            u"title": u"Lol",
            u"backoff_factor": 1,
            u"subscribers": 1,
            u"id": "http://foo.com",
        })

    def test_favicon_model(self):
        fav = Favicon(url='http://example.com/')
        self.assertEqual('%s' % fav, 'Favicon for http://example.com/')
        self.assertEqual(fav.favicon_img(), '(None)')
        fav.favicon = 'foo.png'
        self.assertEqual(fav.favicon_img(), '<img src="/media/foo.png">')

    @patch("requests.get")
    def test_entry_model_behaviour(self, get):
        """Behaviour of the `Entry` model"""
        get.return_value = responses(304)
        feed = FeedFactory.create()
        entry = feed.entries.create(title='My title',
                                    user=feed.category.user,
                                    date=timezone.now())
        # __unicode__
        self.assertEqual('%s' % entry, 'My title')

        # get_absolute_url()
        self.assertEqual('/entries/%s/' % entry.id, entry.get_absolute_url())

    @patch("requests.get")
    def test_handle_etag(self, get):
        get.return_value = responses(200, 'sw-all.xml',
                                     headers={'etag': 'foo',
                                              'last-modified': 'bar'})
        FeedFactory.create()
        data = job_details(UniqueFeed.objects.get().url,
                           connection=get_redis_connection())
        self.assertEqual(data['etag'], 'foo')
        self.assertEqual(data['modified'], 'bar')

    @patch('requests.get')
    def test_invalid_content(self, get):
        """Behaviour of the ``Feed`` model"""
        get.return_value = responses(304)
        feed = Feed(url='http://example.com/')
        entry = Entry(
            feed=feed,
            subtitle='<a href="http://mozillaopennews.org]/">OpenNews</a>')
        self.assertEqual(
            entry.content,
            '<a href="http://mozillaopennews.org%5D/">OpenNews</a>')

    def test_not_scheduled_last_update(self):
        u = UniqueFeed('ĥttp://example.com')
        self.assertIsNone(u.last_update)
