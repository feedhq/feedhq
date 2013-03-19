from datetime import timedelta
from mock import patch

import feedparser

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from feedhq.feeds.management.commands.updatefeeds import TO_UPDATE
from feedhq.feeds.models import UniqueFeed
from feedhq.feeds.utils import USER_AGENT

from .test_feeds import responses


class UpdateTests(TestCase):
    def test_update_feeds(self):
        to_update = TO_UPDATE % 5
        u = UniqueFeed.objects.create(
            url='http://example.com/feed0',
            last_update=timezone.now() - timedelta(hours=1),
        )
        UniqueFeed.objects.create(
            url='http://example.com/feed1',
        )
        with self.assertNumQueries(1):
            feeds = list(UniqueFeed.objects.raw(to_update))
            self.assertEqual(len(feeds), 1)
            self.assertEqual(feeds[0].url, u.url)

        u.delete()
        with self.assertNumQueries(1):
            self.assertEqual(len(list(UniqueFeed.objects.raw(to_update))), 0)

        u = UniqueFeed.objects.create(
            url='http://example.com/backoff',
            last_update=timezone.now() - timedelta(hours=23),
            backoff_factor=10,
        )
        with self.assertNumQueries(1):
            self.assertEqual(len(list(UniqueFeed.objects.raw(to_update))), 0)
        u.backoff_factor = 9
        u.save()
        with self.assertNumQueries(1):
            feeds = list(UniqueFeed.objects.raw(to_update))
            self.assertEqual(len(feeds), 1)
            self.assertEqual(feeds[0].url, u.url)
            self.assertEqual(feeds[0].tm, 180)

        UniqueFeed.objects.update(last_update=timezone.now())
        with self.assertNumQueries(1):
            self.assertEqual(len(list(UniqueFeed.objects.raw(to_update))), 0)

        UniqueFeed.objects.create(
            url='http://example.com/lol',
            last_update=timezone.now() - timedelta(hours=1)
        )

        UniqueFeed.objects.update(
            last_update=timezone.now() - timedelta(hours=54))
        for i in range(3):  # updatefeeds doesn't handle all feeds at once
            call_command('updatefeeds')  # no subscribers -> deletion
        self.assertEqual(UniqueFeed.objects.count(), 0)

        UniqueFeed.objects.create(
            url='http://example.com/foo',
            last_update=timezone.now() - timedelta(hours=1),
        )
        UniqueFeed.objects.create(
            url='http://example.com/bar',
            last_update=timezone.now() - timedelta(hours=1),
            last_loop=timezone.now() - timedelta(hours=1),
        )
        feeds = list(UniqueFeed.objects.raw(to_update))
        self.assertEqual(len(feeds), 2)
        self.assertEqual(feeds[0].url, 'http://example.com/bar')
        self.assertEqual(feeds[1].url, 'http://example.com/foo')

    @patch("requests.get")
    def test_update_call(self, get):
        u = User.objects.create_user('foo', 'foo@example.com', 'pass')
        c = u.categories.create(name='foo', slug='foo')
        get.return_value = responses(304)
        c.feeds.create(url='http://example.com/test')

        self.assertEqual(UniqueFeed.objects.count(), 1)
        get.assert_called_with(
            'http://example.com/test',
            headers={'Accept': feedparser.ACCEPT_HEADER,
                     'User-Agent': USER_AGENT % '1 subscriber'},
            timeout=10)

        call_command('updatefeeds')
        self.assertEqual(UniqueFeed.objects.count(), 1)
