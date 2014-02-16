import time

from datetime import timedelta
from mock import patch

import feedparser
import times

from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from django_push.subscriber.models import Subscription
from rache import pending_jobs, delete_job

from feedhq.feeds.models import UniqueFeed, timedelta_to_seconds
from feedhq.feeds.tasks import store_entries
from feedhq.feeds.utils import USER_AGENT
from feedhq.profiles.models import User
from feedhq.utils import get_redis_connection

from .factories import FeedFactory, UserFactory
from . import responses, ClearRedisTestCase, data_file, patch_job


class UpdateTests(ClearRedisTestCase):
    def test_update_feeds(self):
        u = UniqueFeed.objects.create(
            url='http://example.com/feed0',
        )
        u.schedule()
        patch_job(
            u.url,
            last_update=(timezone.now() - timedelta(hours=1)).strftime('%s')
        )
        u.schedule()
        UniqueFeed.objects.create(
            url='http://example.com/feed1',
        ).schedule()
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60,
                connection=get_redis_connection()))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['id'], u.url)

        u.delete()
        delete_job(u.url, connection=get_redis_connection())
        with self.assertNumQueries(0):
            urls = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60,
                connection=get_redis_connection()))
            self.assertEqual(len(urls), 0)

        u = UniqueFeed.objects.create(
            url='http://example.com/backoff',
        )
        u.schedule()
        patch_job(
            u.url, backoff_factor=10,
            last_update=(timezone.now() - timedelta(hours=28)).strftime('%s')
        )
        u.schedule()
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60,
                connection=get_redis_connection()))
            self.assertEqual(len(jobs), 0)
        patch_job(u.url, backoff_factor=9)
        u.schedule()
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60,
                connection=get_redis_connection()))
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]['id'], u.url)
            self.assertEqual(
                UniqueFeed.TIMEOUT_BASE * jobs[0]['backoff_factor'], 180)

        patch_job(u.url, last_update=int(time.time()))
        u.schedule()
        with self.assertNumQueries(0):
            jobs = list(pending_jobs(
                limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60,
                connection=get_redis_connection()))
            self.assertEqual(len(jobs), 0)

        UniqueFeed.objects.create(
            url='http://example.com/lol',
        )

        for u in UniqueFeed.objects.all():
            patch_job(u.url, last_update=(
                timezone.now() - timedelta(hours=54)).strftime('%s'))

        # No subscribers -> deletion
        with self.assertNumQueries(2):
            call_command('delete_unsubscribed')
        self.assertEqual(UniqueFeed.objects.count(), 0)

        u = UniqueFeed.objects.create(
            url='http://example.com/foo',
        )
        u.schedule()
        patch_job(
            u.url,
            last_update=(timezone.now() - timedelta(hours=2)).strftime('%s'))
        u.schedule()
        u = UniqueFeed.objects.create(
            url='http://example.com/bar',
        )
        u.schedule()
        patch_job(
            u.url,
            last_update=(timezone.now() - timedelta(hours=2)).strftime('%s'))
        u.schedule()
        jobs = list(pending_jobs(
            limit=5, reschedule_in=UniqueFeed.UPDATE_PERIOD * 60,
            connection=get_redis_connection()))
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

        with self.assertNumQueries(1):
            call_command('add_missing')

    @patch("requests.get")
    def test_updatefeeds_queuing(self, get):
        get.return_value = responses(304)

        for i in range(24):
            f = FeedFactory.create()
            patch_job(f.url, last_update=(
                timezone.now() - timedelta(hours=10)).strftime('%s'))
            UniqueFeed.objects.get(url=f.url).schedule()

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

        parsed = feedparser.parse(data_file('sw-all.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )

        with self.assertNumQueries(2):  # no insert
            store_entries(feed.url, data)

        last_updates = feed.user.last_updates()
        self.assertEqual(last_updates, {})

        feed2 = FeedFactory.create(url=feed.url)
        self.assertEqual(UniqueFeed.objects.count(), 1)
        call_command('delete_unsubscribed')
        self.assertEqual(UniqueFeed.objects.count(), 1)

        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )
        with self.assertNumQueries(5):  # insert
            store_entries(feed.url, data)

        self.assertEqual(feed.entries.count(), 0)
        self.assertEqual(feed2.entries.count(), 30)
        last_updates = feed2.user.last_updates()
        self.assertEqual(last_updates.keys(), [feed2.url])

    @patch('requests.get')
    def test_same_guids(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()

        parsed = feedparser.parse(data_file('aldaily-06-27.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )

        with self.assertNumQueries(5):
            store_entries(feed.url, data)
        self.assertEqual(feed.entries.count(), 4)

        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )
        with self.assertNumQueries(2):
            store_entries(feed.url, data)
        self.assertEqual(feed.entries.count(), 4)

        parsed = feedparser.parse(data_file('aldaily-06-30.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )

        with self.assertNumQueries(5):
            store_entries(feed.url, data)
        self.assertEqual(feed.entries.count(), 10)

    @patch("requests.get")
    def test_empty_guid(self, get):
        get.return_value = responses(304)

        parsed = feedparser.parse(data_file('no-guid.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )
        feed = FeedFactory.create()
        with self.assertNumQueries(5):
            store_entries(feed.url, data)
        self.assertTrue(feed.entries.get().guid)

        feed.entries.all().delete()

        parsed = feedparser.parse(data_file('no-link-guid.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )
        feed = FeedFactory.create()
        with self.assertNumQueries(5):
            store_entries(feed.url, data)
        self.assertTrue(feed.entries.get().guid)

    @patch("requests.get")
    def test_ttl(self, get):
        get.return_value = responses(304)
        user = UserFactory.create(ttl=3)
        feed = FeedFactory.create(user=user, category__user=user)

        parsed = feedparser.parse(data_file('bruno.im.atom'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )
        with self.assertNumQueries(2):
            store_entries(feed.url, data)
        self.assertEqual(feed.entries.count(), 0)

    @patch("requests.get")
    def test_no_content(self, get):
        get.return_value = responses(304)
        parsed = feedparser.parse(data_file('no-content.xml'))
        data = filter(
            None,
            [UniqueFeed.objects.entry_data(
                entry, parsed) for entry in parsed.entries]
        )
        self.assertEqual(data, [])

    @patch("requests.get")
    def test_schedule_in(self, get):
        get.return_value = responses(304)

        f = FeedFactory.create()
        secs = timedelta_to_seconds(UniqueFeed.objects.get().schedule_in)
        self.assertTrue(3598 <= secs < 3600)

        patch_job(f.url, backoff_factor=2)
        secs = timedelta_to_seconds(UniqueFeed.objects.get().schedule_in)
        self.assertTrue(secs > 10000)

    def test_clean_rq(self):
        r = get_redis_connection()
        self.assertEqual(len(r.keys('rq:job:*')), 0)
        r.hmset('rq:job:abc', {'bar': 'baz'})
        r.hmset('rq:job:def', {'created_at': times.format(times.now(), 'UTC')})
        r.hmset('rq:job:123', {
            'created_at': times.format(
                times.now() - timedelta(days=10), 'UTC')})
        self.assertEqual(len(r.keys('rq:job:*')), 3)
        call_command('clean_rq')
        self.assertEqual(len(r.keys('rq:job:*')), 2)

    @patch('requests.post')
    @patch('requests.get')
    def test_ensure_subscribed(self, get, post):
        get.return_value = responses(200, 'hub.atom')
        post.return_value = responses(202)

        feed = FeedFactory.create()
        subscription = Subscription.objects.get()
        post.assert_called_with(
            u'http://pubsubhubbub.appspot.com/',
            data={
                u'hub.callback': u'http://localhost/subscriber/{0}/'.format(
                    subscription.pk),
                u'hub.verify': [u'sync', u'async'],
                u'hub.topic': feed.url,
                u'hub.mode': u'subscribe'},
            timeout=None,
            auth=None)
        self.assertEqual(feed.url, subscription.topic)

        post.reset_mock()
        self.assertFalse(post.called)
        subscription.lease_expiration = timezone.now()
        subscription.save()

        feed.delete()
        cache.delete(u'pshb:{0}'.format(feed.url))
        feed = FeedFactory.create(url=feed.url)
        post.assert_called_with(
            u'http://pubsubhubbub.appspot.com/',
            data={
                u'hub.callback': u'http://localhost/subscriber/{0}/'.format(
                    subscription.pk),
                u'hub.verify': [u'sync', u'async'],
                u'hub.topic': feed.url,
                u'hub.mode': u'subscribe'},
            timeout=None,
            auth=None)

        post.reset_mock()
        self.assertFalse(post.called)
        subscription.lease_expiration = timezone.now() + timedelta(days=5)
        subscription.save()
        feed.delete()
        cache.delete(u'pshb:{0}'.format(feed.url))
        feed = FeedFactory.create(url=feed.url)
        post.assert_called_with(
            u'http://pubsubhubbub.appspot.com/',
            data={
                u'hub.callback': u'http://localhost/subscriber/{0}/'.format(
                    subscription.pk),
                u'hub.verify': [u'sync', u'async'],
                u'hub.topic': feed.url,
                u'hub.mode': u'subscribe'},
            timeout=None,
            auth=None)

        post.reset_mock()
        self.assertFalse(post.called)
        subscription.verified = True
        subscription.save()
        feed.delete()
        cache.delete(u'pshb:{0}'.format(feed.url))
        feed = FeedFactory.create(url=feed.url)
        self.assertFalse(post.called)
