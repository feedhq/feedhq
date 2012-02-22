from settings import *

TESTS = True

# Silencing log calls
LOGGING['loggers']['feedupdater']['level'] = 'ERROR'
LOGGING['loggers']['ratelimitbackend']['level'] = 'ERROR'

MEDIA_ROOT = os.path.join(HERE, 'test_media')
