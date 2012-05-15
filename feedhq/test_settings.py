import warnings
warnings.simplefilter('always')

from default_settings import *  # noqa

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'feedhq',
        'USER': 'postgres',
    },
}

TESTS = True

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
LOGGING['loggers']['feedupdater']['level'] = 'ERROR'
LOGGING['loggers']['ratelimitbackend']['level'] = 'ERROR'

MEDIA_ROOT = os.path.join(HERE, 'test_media')
