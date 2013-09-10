from django.test import TestCase
from mock import patch

from feedhq.feeds.models import Favicon, Feed

from .factories import FeedFactory
from . import responses


class FaviconTests(TestCase):
    @patch("requests.get")
    def test_existing_favicon_new_feed(self, get):
        get.return_value = responses(304)
        FeedFactory.create(url='http://example.com/feed')
        self.assertEqual(Feed.objects.values_list('favicon', flat=True)[0], '')

        # Simulate a 1st call of update_favicon which creates a Favicon entry
        Favicon.objects.create(url='http://example.com/feed',
                               favicon='favicons/example.com.ico')

        Favicon.objects.update_favicon('http://example.com/feed')
        self.assertEqual(Feed.objects.values_list('favicon', flat=True)[0],
                         'favicons/example.com.ico')
