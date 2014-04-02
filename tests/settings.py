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

MEDIA_ROOT = os.path.join(BASE_DIR, 'test_media')
