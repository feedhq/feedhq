import socket
from unittest.mock import patch, PropertyMock

import feedparser
from django.core.management import call_command
from django.utils import timezone
from feedhq import es
from feedhq.feeds.models import Favicon, Feed, UniqueFeed
from feedhq.feeds.tasks import update_feed
from feedhq.feeds.utils import epoch_to_utc, FAVICON_FETCHER, USER_AGENT
from feedhq.utils import get_redis_connection
from rache import job_details, schedule_job
from requests import RequestException
from requests.packages.urllib3.exceptions import (DecodeError,
                                                  LocationParseError)
from rq.timeouts import JobTimeoutException
from six.moves.http_client import IncompleteRead

from . import patch_job, TestCase
from .factories import FeedFactory, UserFactory
from .test_feeds import data_file, responses


class UpdateTests(TestCase):
    @patch("requests.get")
    def test_parse_error(self, get):
        get.side_effect = LocationParseError("Failed to parse url")
        FeedFactory.create()
        unique = UniqueFeed.objects.get()
        self.assertTrue(unique.muted)
        self.assertEqual(unique.error, UniqueFeed.PARSE_ERROR)

    @patch("requests.get")
    def test_decode_error(self, get):
        get.side_effect = DecodeError("Received response with content-encoding"
                                      ": gzip, but failed to decode it.")
        FeedFactory.create()
        unique = UniqueFeed.objects.get()
        data = job_details(unique.url, connection=get_redis_connection())
        self.assertEqual(data['backoff_factor'], 2)
        self.assertEqual(data['error'], UniqueFeed.DECODE_ERROR)

    @patch("requests.get")
    def test_incomplete_read(self, get):
        get.side_effect = IncompleteRead("0 bytes read")
        FeedFactory.create()
        f = UniqueFeed.objects.get()
        self.assertFalse(f.muted)
        data = job_details(f.url, connection=get_redis_connection())
        self.assertEqual(data['error'], f.CONNECTION_ERROR)

    @patch("requests.get")
    def test_socket_timeout(self, get):
        m = get.return_value
        type(m).content = PropertyMock(side_effect=socket.timeout)
        FeedFactory.create()
        f = UniqueFeed.objects.get()
        self.assertFalse(f.muted)
        data = job_details(f.url, connection=get_redis_connection())
        self.assertEqual(data['error'], f.TIMEOUT)

    @patch('requests.head')
    @patch('requests.get')
    def test_ctype(self, get, head):
        # Updatefeed doesn't fail if content-type is missing
        head.return_value = responses(200)
        get.return_value = responses(200, 'sw-all.xml', headers={})
        feed = FeedFactory.create()
        update_feed(feed.url)
        get.assert_called_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER},
            timeout=10, auth=None)

        get.return_value = responses(200, 'sw-all.xml',
                                     headers={'Content-Type': None})
        update_feed(feed.url)
        get.assert_called_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER},
            timeout=10, auth=None)

    @patch('requests.head')
    @patch('requests.get')
    def test_permanent_redirects(self, get, head):
        """Updating the feed if there's a permanent redirect"""
        head.return_value = responses(200)
        get.return_value = responses(
            301, redirection='permanent-atom10.xml',
            headers={'Content-Type': 'application/rss+xml'})
        feed = FeedFactory.create()
        feed = Feed.objects.get(pk=feed.id)
        self.assertEqual(feed.url, 'permanent-atom10.xml')

    @patch('requests.get')
    def test_temporary_redirect(self, get):
        """Don't update the feed if the redirect is not 301"""
        get.return_value = responses(
            302, redirection='atom10.xml',
            headers={'Content-Type': 'application/rss+xml'})
        feed = FeedFactory.create()
        get.assert_called_with(
            feed.url, timeout=10, auth=None,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER},
        )
        feed = Feed.objects.get(pk=feed.id)
        self.assertNotEqual(feed.url, 'atom10.xml')

    @patch('requests.head')
    @patch('requests.get')
    def test_entry_redirect(self, get, head):
        head.return_value = responses(301, path='https://example.com',
                                      redirection='')
        get.return_value = responses(200, 'atom10.xml')
        # This test will fail in 2105. If so, increase the delay.
        feed = FeedFactory.create(user__ttl=365*100)
        self.assertEqual(len(head.call_args_list), 1)
        entries = es.manager.user(feed.user)
        [entry] = entries.fetch()['hits']
        self.assertEqual(entry.link, 'https://example.com')

    @patch('requests.head')
    @patch('requests.get')
    def test_content_handling(self, get, head):
        """The content section overrides the subtitle section"""
        head.return_value = responses(200)
        get.return_value = responses(200, 'atom10.xml')
        user = UserFactory.create(ttl=99999)
        FeedFactory.create(name='Content', url='http://atom10.xml', user=user)
        [entry] = es.manager.user(user).fetch(annotate=user)['hits']
        self.assertEqual(entry.sanitized_content(),
                         "<div>Watch out for <span> nasty tricks</span></div>")

        self.assertEqual(entry.author, 'Mark Pilgrim (mark@example.org)')

    @patch('requests.get')
    def test_gone(self, get):
        """Muting the feed if the status code is 410"""
        get.return_value = responses(410)
        FeedFactory.create(url='http://gone.xml')
        feed = UniqueFeed.objects.get(url='http://gone.xml')
        self.assertTrue(feed.muted)

    @patch('requests.get')
    def test_errors(self, get):
        codes = [400, 401, 403, 404, 500, 502, 503]

        def get_side_effect():
            yield responses(304)
            for code in codes:
                yield responses(code)
        get.side_effect = get_side_effect()
        feed = FeedFactory.create()
        self.assertEqual(len(get.call_args_list), 1)

        for code in codes:
            get.return_value = responses(code)
            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            self.assertEqual(feed.job_details.get('error'), None)
            self.assertEqual(feed.job_details['backoff_factor'], 1)
            feed.schedule()
            data = job_details(feed.url, connection=get_redis_connection())

            update_feed(feed.url, backoff_factor=data['backoff_factor'])

            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            data = job_details(feed.url, connection=get_redis_connection())
            self.assertEqual(data['error'], code)
            self.assertEqual(data['backoff_factor'], 2)

            # Restore status for next iteration
            schedule_job(feed.url, backoff_factor=1, error=None, schedule_in=0)
            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertEqual(feed.job_details.get('error'), None)

    @patch('requests.get')
    def test_too_many_requests(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()

        get.return_value = responses(429)
        update_feed(feed.url, backoff_factor=1)
        data = job_details(feed.url, connection=get_redis_connection())
        # retry in 1 min
        self.assertTrue(
            58 <
            (epoch_to_utc(data['schedule_at']) - timezone.now()).seconds <
            60
        )

    @patch('requests.get')
    def test_too_many_requests_retry(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()

        get.return_value = responses(429, headers={'Retry-After': '3600'})
        update_feed(feed.url, backoff_factor=1)
        data = job_details(feed.url, connection=get_redis_connection())
        # Retry in 1 hour
        self.assertTrue(
            3590 <
            (epoch_to_utc(data['schedule_at']) - timezone.now()).seconds <
            3600
        )

        # Other requests to same domain
        get.reset_mock()
        get.assert_not_called()
        update_feed(feed.url, backoff_factor=1)
        get.assert_not_called()

    @patch('requests.get')
    def test_backoff(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()
        feed = UniqueFeed.objects.get(url=feed.url)
        detail = feed.job_details
        self.assertFalse('error' in detail)
        self.assertEqual(detail['backoff_factor'], 1)
        feed.schedule()
        data = job_details(feed.url, connection=get_redis_connection())

        get.return_value = responses(502)
        for i in range(12):
            update_feed(feed.url, backoff_factor=data['backoff_factor'])
            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            data = job_details(feed.url, connection=get_redis_connection())
            self.assertEqual(data['error'], 502)
            self.assertEqual(data['backoff_factor'], min(i + 2, 10))

        get.side_effect = RequestException
        feed = UniqueFeed.objects.get()
        patch_job(feed.url, error=None, backoff_factor=1)
        data = job_details(feed.url, connection=get_redis_connection())

        for i in range(12):
            update_feed(feed.url, backoff_factor=data['backoff_factor'])
            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            data = job_details(feed.url, connection=get_redis_connection())
            self.assertEqual(data['error'], 'timeout')
            self.assertEqual(data['backoff_factor'], min(i + 2, 10))

    @patch("requests.get")
    def test_etag_modified(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()
        update_feed(feed.url, etag='etag', modified='1234', subscribers=2)
        get.assert_called_with(
            feed.url,
            headers={
                'User-Agent': USER_AGENT % '2 subscribers',
                'Accept': feedparser.ACCEPT_HEADER,
                'If-None-Match': b'etag',
                'If-Modified-Since': b'1234',
            }, timeout=10, auth=None)

    @patch("requests.get")
    def test_restore_backoff(self, get):
        get.return_value = responses(304)
        FeedFactory.create()
        feed = UniqueFeed.objects.get()
        feed.error = 'timeout'
        feed.backoff_factor = 5
        feed.save()
        update_feed(feed.url, error=feed.error,
                    backoff_factor=feed.backoff_factor)

        data = job_details(feed.url, connection=get_redis_connection())
        self.assertEqual(data['backoff_factor'], 1)
        self.assertTrue('error' not in data)

    @patch('requests.head')
    @patch('requests.get')
    def test_no_date_and_304(self, get, head):
        """If the feed does not have a date, we'll have to find one.
        Also, since we update it twice, the 2nd time it's a 304 response."""
        head.return_value = responses(200)
        get.return_value = responses(200, 'no-date.xml')
        feed = FeedFactory.create()

        # Update the feed twice and make sure we don't index the content twice
        update_feed(feed.url)
        feed1 = Feed.objects.get(pk=feed.id)
        count1 = feed1.entries.count()

        update_feed(feed1.url)
        feed2 = Feed.objects.get(pk=feed1.id)
        count2 = feed2.entries.count()

        self.assertEqual(count1, count2)

    @patch("requests.get")
    def test_uniquefeed_deletion(self, get):
        get.return_value = responses(304)
        f = UniqueFeed.objects.create(url='http://example.com')
        self.assertEqual(UniqueFeed.objects.count(), 1)
        call_command('delete_unsubscribed')
        UniqueFeed.objects.update_feed(f.url)
        self.assertEqual(UniqueFeed.objects.count(), 0)

    @patch('requests.head')
    @patch('requests.get')
    def test_no_link(self, get, head):
        head.return_value = responses(200)
        get.return_value = responses(200, 'rss20.xml')
        user = UserFactory.create(ttl=99999)
        feed = FeedFactory.create(user=user, category__user=user)
        update_feed(feed.url)

        count = self.counts(user, all={})['all']
        self.assertEqual(count, 1)

        get.return_value = responses(200, 'no-link.xml')
        feed.url = 'http://no-link.xml'
        feed.save(update_fields=['url'])
        update_feed(feed.url)

        count = self.counts(user, all={})['all']
        self.assertEqual(count, 1)

    @patch('requests.get')
    def test_task_timeout_handling(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()
        get.side_effect = JobTimeoutException
        self.assertEqual(
            UniqueFeed.objects.get().job_details['backoff_factor'], 1)
        update_feed(feed.url)
        data = job_details(feed.url, connection=get_redis_connection())
        self.assertEqual(data['backoff_factor'], 2)


class FaviconTests(TestCase):
    @patch("requests.get")
    def test_declared_favicon(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create(url='http://example.com/feed')
        patch_job(feed.url, link='http://example.com')

        with open(data_file('bruno.im.png'), 'rb') as f:
            fav = f.read()

        class Response:
            status_code = 200
            content = fav
            headers = {'foo': 'bar'}
        get.reset_mock()
        get.return_value = Response()
        Favicon.objects.update_favicon(feed.url)
        get.assert_called_with(
            'http://example.com/favicon.ico',
            headers={'User-Agent': FAVICON_FETCHER},
            timeout=10,
        )

    @patch("requests.get")
    def test_favicon_empty_document(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create(url='http://example.com/feed')
        patch_job(feed.url, link='http://example.com')

        class Response:
            status_code = 200
            content = '<?xml version="1.0" encoding="iso-8859-1"?>'
            headers = {}
        get.return_value = Response()
        Favicon.objects.update_favicon(feed.url)

    @patch("requests.get")
    def test_favicon_parse_error(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create(url='http://example.com/feed')
        patch_job(feed.url, link='http://example.com')

        get.side_effect = LocationParseError("Failed to parse url")
        Favicon.objects.update_favicon(feed.url)
