import warnings
warnings.simplefilter('always')

from settings import *

TESTS = True

EMAIL_HOST = 'dummy'

API_KEYS = {
    'readitlater': 'test read it later API key',
}

# Silencing log calls
LOGGING['loggers']['feedupdater']['level'] = 'ERROR'
LOGGING['loggers']['ratelimitbackend']['level'] = 'ERROR'

MEDIA_ROOT = os.path.join(HERE, 'test_media')
