import feedparser

from django.core.management import call_command
from httplib import IncompleteRead
from mock import patch
from rache import job_details
from requests import RequestException
from requests.packages.urllib3.exceptions import LocationParseError
from rq.timeouts import JobTimeoutException

from feedhq.feeds.models import Favicon, UniqueFeed, Feed, Entry
from feedhq.feeds.tasks import update_feed
from feedhq.feeds.utils import FAVICON_FETCHER, USER_AGENT

from .factories import FeedFactory
from .test_feeds import test_file, responses
from . import ClearRacheTestCase


class UpdateTests(ClearRacheTestCase):
    @patch("requests.get")
    def test_parse_error(self, get):
        get.side_effect = LocationParseError("Failed to parse url")
        FeedFactory.create()
        unique = UniqueFeed.objects.get()
        self.assertTrue(unique.muted)
        self.assertEqual(unique.error, UniqueFeed.PARSE_ERROR)

    @patch("requests.get")
    def test_incomplete_read(self, get):
        get.side_effect = IncompleteRead("0 bytes read")
        FeedFactory.create()
        f = UniqueFeed.objects.get()
        self.assertFalse(f.muted)
        data = job_details(f.url)
        self.assertEqual(data['error'], f.CONNECTION_ERROR)

    @patch('requests.get')
    def test_ctype(self, get):
        # Updatefeed doesn't fail if content-type is missing
        get.return_value = responses(200, 'sw-all.xml', headers={})
        feed = FeedFactory.create()
        update_feed(feed.url)
        get.assert_called_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

        get.return_value = responses(200, 'sw-all.xml',
                                     headers={'Content-Type': None})
        update_feed(feed.url)
        get.assert_called_with(
            feed.url,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER}, timeout=10)

    @patch('requests.get')
    def test_permanent_redirects(self, get):
        """Updating the feed if there's a permanent redirect"""
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
            feed.url, timeout=10,
            headers={'User-Agent': USER_AGENT % '1 subscriber',
                     'Accept': feedparser.ACCEPT_HEADER},
        )
        feed = Feed.objects.get(pk=feed.id)
        self.assertNotEqual(feed.url, 'atom10.xml')

    @patch('requests.get')
    def test_content_handling(self, get):
        """The content section overrides the subtitle section"""
        get.return_value = responses(200, 'atom10.xml')
        FeedFactory.create(name='Content', url='atom10.xml')
        entry = Entry.objects.get()
        self.assertEqual(entry.sanitized_content(),
                         "<div>Watch out for <span> nasty tricks</span></div>")

        self.assertEqual(entry.author, 'Mark Pilgrim (mark@example.org)')

    @patch('requests.get')
    def test_gone(self, get):
        """Muting the feed if the status code is 410"""
        get.return_value = responses(410)
        FeedFactory.create(url='gone.xml')
        feed = UniqueFeed.objects.get(url='gone.xml')
        self.assertTrue(feed.muted)

    @patch('requests.get')
    def test_errors(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()

        for code in [400, 401, 403, 404, 500, 502, 503]:
            get.return_value = responses(code)
            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            self.assertEqual(feed.error, None)
            self.assertEqual(feed.backoff_factor, 1)
            feed.schedule()
            data = job_details(feed.url)

            update_feed(feed.url, backoff_factor=data['backoff_factor'])

            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            data = job_details(feed.url)
            self.assertEqual(data['error'], code)
            self.assertEqual(data['backoff_factor'], 2)

            # Restore status for next iteration
            feed.backoff_factor = 1
            feed.error = None
            feed.save(update_fields=['backoff_factor', 'error'])
            feed.schedule()

    @patch('requests.get')
    def test_backoff(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()
        feed = UniqueFeed.objects.get(url=feed.url)
        self.assertEqual(feed.error, None)
        self.assertEqual(feed.backoff_factor, 1)
        feed.schedule()
        data = job_details(feed.url)

        get.return_value = responses(502)
        for i in range(12):
            update_feed(feed.url, backoff_factor=data['backoff_factor'])
            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            data = job_details(feed.url)
            self.assertEqual(data['error'], 502)
            self.assertEqual(data['backoff_factor'], min(i + 2, 10))

        get.side_effect = RequestException
        feed = UniqueFeed.objects.get()
        feed.error = None
        feed.backoff_factor = 1
        feed.save()
        feed.schedule()
        data = job_details(feed.url)

        for i in range(12):
            update_feed(feed.url, backoff_factor=data['backoff_factor'])
            feed = UniqueFeed.objects.get(url=feed.url)
            self.assertFalse(feed.muted)
            data = job_details(feed.url)
            self.assertEqual(data['error'], 'timeout')
            self.assertEqual(data['backoff_factor'], min(i + 2, 10))

    @patch("requests.get")
    def test_etag_modified(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()
        update_feed(feed.url, etag='etag', last_modified='1234', subscribers=2)
        get.assert_called_with(
            feed.url,
            headers={
                'User-Agent': USER_AGENT % '2 subscribers',
                'Accept': feedparser.ACCEPT_HEADER,
                'If-None-Match': 'etag',
                'If-Modified-Since': '1234',
            }, timeout=10)

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

        data = job_details(feed.url)
        self.assertEqual(data['backoff_factor'], 1)
        self.assertTrue('error' not in data)

    @patch('requests.get')
    def test_no_date_and_304(self, get):
        """If the feed does not have a date, we'll have to find one.
        Also, since we update it twice, the 2nd time it's a 304 response."""
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
        f = UniqueFeed.objects.create(url='example.com')
        self.assertEqual(UniqueFeed.objects.count(), 1)
        call_command('delete_unsubscribed')
        UniqueFeed.objects.update_feed(f.url)
        self.assertEqual(UniqueFeed.objects.count(), 0)

    @patch('requests.get')
    def test_no_link(self, get):
        get.return_value = responses(200, 'rss20.xml')
        feed = FeedFactory.create()
        update_feed(feed.url)
        self.assertEqual(Entry.objects.count(), 1)

        get.return_value = responses(200, 'no-link.xml')
        feed.url = 'no-link.xml'
        feed.save(update_fields=['url'])
        update_feed(feed.url)
        self.assertEqual(Entry.objects.count(), 1)

    @patch('requests.get')
    def test_task_timeout_handling(self, get):
        get.return_value = responses(304)
        feed = FeedFactory.create()
        get.side_effect = JobTimeoutException
        self.assertEqual(UniqueFeed.objects.get().backoff_factor, 1)
        update_feed(feed.url)
        data = job_details(feed.url)
        self.assertEqual(data['backoff_factor'], 2)


class FaviconTests(ClearRacheTestCase):
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

    @patch("requests.get")
    def test_favicon_empty_document(self, get):
        class Response:
            status_code = 200
            content = '<?xml version="1.0" encoding="iso-8859-1"?>'
            headers = {}
        get.return_value = Response()
        Favicon.objects.update_favicon('http://example.com')

    @patch("requests.get")
    def test_favicon_parse_error(self, get):
        get.side_effect = LocationParseError("Failed to parse url")
        Favicon.objects.update_favicon('http://example.com')
