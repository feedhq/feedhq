import sys
import warnings
warnings.simplefilter('always')

from feedhq.settings import *  # noqa

SECRET_KEY = 'test secret key'

TESTS = True

PASSWORD_HASHERS = [
    'tests.hashers.NotHashingHasher',
]

RQ_EAGER = True

STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

EMAIL_HOST = 'dummy'

API_KEYS = {
    'readitlater': 'test read it later API key',
}

INSTAPAPER = READABILITY = {
    'CONSUMER_KEY': 'consumer key',
    'CONSUMER_SECRET': 'consumer secret',
}

# Silencing log calls
if '-v2' not in sys.argv:
    LOGGING['loggers']['ratelimitbackend']['level'] = 'ERROR'
    LOGGING['loggers']['feedhq']['level'] = 'ERROR'
    LOGGING['loggers']['elasticsearch']['level'] = 'ERROR'

MEDIA_ROOT = os.path.join(BASE_DIR, 'test_media')

ES_INDEX = 'test-feedhq'
ES_ALIAS_TEMPLATE = 'test-feedhq-{0}'
ES_SHARDS = 1
ES_REPLICAS = 0

TEST_RUNNER = 'tests.runner.ESTestSuiteRunner'
