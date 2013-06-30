import time

from datetime import timedelta
from mock import patch

import feedparser

from django.core.management import call_command
from django.utils import timezone
from rache import pending_jobs, delete_job, schedule_job

from feedhq.feeds.models import UniqueFeed, timedelta_to_seconds
from feedhq.feeds.tasks import store_entries
from feedhq.feeds.utils import USER_AGENT
from feedhq.profiles.models import User

from .factories import FeedFactory
from . import responses, ClearRacheTestCase, test_file


class UpdateTests(ClearRacheTestCase):
    def test_update_feeds(self):
        u = UniqueFeed.objects.create(
            url='http://example.com/feed0',
            last_update=timezone.now() - timedelta(hours=1),
        )
        u.schedule()
        UniqueFeed.objects.create(
            url='http://example.com/feed1',
        ).schedule()
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['id'], u.url)

        u.delete()
        delete_job(u.url)
        with self.assertNumQueries(0):
            urls = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60))
            self.assertEqual(len(urls), 0)

        u = UniqueFeed.objects.create(
            url='http://example.com/backoff',
            last_update=timezone.now() - timedelta(hours=28),
            backoff_factor=10,
        )
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60))
            self.assertEqual(len(jobs), 0)
        u.backoff_factor = 9
        u.save()
        u.schedule()
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['id'], u.url)
            self.assertEqual(
                UniqueFeed.TIMEOUT_BASE * jobs[0]['backoff_factor'], 180)

        UniqueFeed.objects.update(last_update=timezone.now())
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60))
            self.assertEqual(len(jobs), 0)

        UniqueFeed.objects.create(
            url='http://example.com/lol',
        )

        UniqueFeed.objects.update(
            last_update=timezone.now() - timedelta(hours=54))

        # No subscribers -> deletion
        with self.assertNumQueries(2):
            call_command('delete_unsubscribed')
        self.assertEqual(UniqueFeed.objects.count(), 0)

        UniqueFeed.objects.create(
            url='http://example.com/foo',
            last_update=timezone.now() - timedelta(hours=2),
        ).schedule()
        UniqueFeed.objects.create(
            url='http://example.com/bar',
            last_update=timezone.now() - timedelta(hours=2),
            last_loop=timezone.now() - timedelta(hours=2),
        ).schedule()
        jobs = list(pending_jobs(
            limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60))
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]['id'], 'http://example.com/bar')
        self.assertEqual(jobs[1]['id'], 'http://example.com/foo')

    @patch("requests.get")
    def test_update_call(self, get):
        u = User.objects.create_user('foo', 'foo@example.com', 'pass')
        c = u.categories.create(name='foo', slug='foo')
        get.return_value = responses(304)
        c.feeds.create(url='http://example.com/test', user=c.user)

        self.assertEqual(UniqueFeed.objects.count(), 1)
        get.assert_called_with(
            'http://example.com/test',
            headers={'Accept': feedparser.ACCEPT_HEADER,
                     'User-Agent': USER_AGENT % '1 subscriber'},
            timeout=10)

        call_command('delete_unsubscribed')
        self.assertEqual(UniqueFeed.objects.count(), 1)

    @patch("requests.get")
    def test_add_missing(self, get):
        get.return_value = responses(304)

        feed = FeedFactory.create()
        FeedFactory.create(url=feed.url)
        FeedFactory.create(url=feed.url)
        FeedFactory.create()

        UniqueFeed.objects.all().delete()
        with self.assertNumQueries(2):
            call_command('add_missing')

        unique = UniqueFeed.objects.get(url=feed.url)
        self.assertEqual(unique.url, feed.url)
        self.assertEqual(unique.subscribers, 3)
        other = UniqueFeed.objects.exclude(pk=unique.pk).get()
        self.assertEqual(other.subscribers, 1)

        with self.assertNumQueries(1):
            call_command('add_missing')

    @patch("requests.get")
    def test_updatefeeds_queuing(self, get):
        get.return_value = responses(304)

        for i in range(24):
            FeedFactory.create()
        UniqueFeed.objects.all().update(
            last_loop=timezone.now() - timedelta(hours=10),
            last_update=timezone.now() - timedelta(hours=10),
        )

        unique = UniqueFeed.objects.all()[0]
        with self.assertNumQueries(1):
            # Select
            call_command('updatefeeds', unique.pk)

        with self.assertNumQueries(1):
            # single select, already scheduled
            call_command('sync_scheduler')

        with self.assertNumQueries(1):
            # count()
            call_command('updatefeeds')

    @patch('requests.get')
    def test_suspending_user(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create(user__is_suspended=True)
        call_command('delete_unsubscribed')
        self.assertEqual(UniqueFeed.objects.count(), 0)

        parsed = feedparser.parse(test_file('sw-all.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )

        with self.assertNumQueries(2):  # no insert
            store_entries(feed.url, data)

        feed2 = FeedFactory.create(url=feed.url)
        self.assertEqual(UniqueFeed.objects.count(), 1)
        call_command('delete_unsubscribed')
        self.assertEqual(UniqueFeed.objects.count(), 1)

        with self.assertNumQueries(5):  # insert
            store_entries(feed.url, data)

        self.assertEqual(feed.entries.count(), 0)
        self.assertEqual(feed2.entries.count(), 30)

    @patch('requests.get')
    def test_same_guids(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()

        parsed = feedparser.parse(test_file('aldaily-06-27.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )

        with self.assertNumQueries(5):
            store_entries(feed.url, data)
        self.assertEqual(feed.entries.count(), 4)

        with self.assertNumQueries(2):
            store_entries(feed.url, data)
        self.assertEqual(feed.entries.count(), 4)

        parsed = feedparser.parse(test_file('aldaily-06-30.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )

        with self.assertNumQueries(5):
            store_entries(feed.url, data)
        self.assertEqual(feed.entries.count(), 10)

    @patch("requests.get")
    def test_schedule_in(self, get):
        get.return_value = responses(304)

        FeedFactory.create()
        secs = timedelta_to_seconds(UniqueFeed.objects.get().schedule_in)
        self.assertTrue(3598 <= secs < 3600)

        UniqueFeed.objects.update(backoff_factor=2)
        secs = timedelta_to_seconds(UniqueFeed.objects.get().schedule_in)
        self.assertTrue(secs > 10000)

    @patch("requests.get")
    def test_scheduler_backup(self, get):
        get.return_value = responses(304)

        feed = FeedFactory.create()
        with self.assertNumQueries(1):
            call_command('backup_scheduler')

        schedule_job(feed.url, schedule_in=10, subscribers=10, etag='foobar',
                     backoff_factor=2, last_update=int(time.time()) + 10,
                     title="f" * 2049)

        with self.assertNumQueries(1):
            call_command('backup_scheduler')

        schedule_job(feed.url, schedule_in=10, title='12')

        with self.assertNumQueries(1):
            call_command('backup_scheduler')

        unique = UniqueFeed.objects.get()
        self.assertEqual(unique.subscribers, 10)
        self.assertEqual(unique.backoff_factor, 2)
        self.assertEqual(unique.etag, 'foobar')
        self.assertEqual(unique.modified, '')
        delta = (unique.last_update - timezone.now()).seconds
        self.assertTrue(5 < delta < 10)

        for i in range(4):
            FeedFactory.create()
        with self.assertNumQueries(5):
            call_command('backup_scheduler')
