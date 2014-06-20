from django.conf import settings
from django.core.management import call_command
from django.test.runner import DiscoverRunner

from feedhq import es


class ESTestSuiteRunner(DiscoverRunner):
    def setup_test_environment(self):
        super(ESTestSuiteRunner, self).setup_test_environment()
        call_command('create_index')
        es.wait_for_yellow()

    def teardown_test_environment(self):
        super(ESTestSuiteRunner, self).teardown_test_environment()
        es.client.indices.delete(settings.ES_INDEX)
