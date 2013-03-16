import dj_database_url
import os
import urlparse

from django.core.urlresolvers import reverse_lazy

BASE_DIR = os.path.dirname(__file__)

DEBUG = os.environ.get('DEBUG', False)
TEMPLATE_DEBUG = DEBUG

# Are we running the tests or a real server?
TESTS = False

TEST_RUNNER = 'discover_runner.DiscoverRunner'
TEST_DISCOVER_TOP_LEVEL = os.path.join(BASE_DIR, os.pardir)
TEST_DISCOVER_ROOT = os.path.join(TEST_DISCOVER_TOP_LEVEL, 'tests')

ADMINS = MANAGERS = ()

DATABASES = {
    'default': dj_database_url.config(
        default='postgres://postgres@localhost:5432/feedhq',
    ),
}

TIME_ZONE = 'UTC'

LANGUAGE_CODE = 'en-us'

USE_I18N = True
USE_L10N = True
USE_TZ = True

SITE_ID = 1

MEDIA_ROOT = os.environ.get('MEDIA_ROOT', os.path.join(BASE_DIR, 'media'))
MEDIA_URL = '/media/'

STATIC_ROOT = os.environ.get('STATIC_ROOT', os.path.join(BASE_DIR, 'static'))
STATIC_URL = '/static/'

SECRET_KEY = os.environ['SECRET_KEY']

ALLOWED_HOSTS = os.environ['ALLOWED_HOSTS'].split()

WSGI_APPLICATION = 'feedhq.wsgi.application'

if not DEBUG:
    STATICFILES_STORAGE = ('django.contrib.staticfiles.storage.'
                           'CachedStaticFilesStorage')

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = SERVER_EMAIL = os.environ['FROM_EMAIL']

AUTHENTICATION_BACKENDS = (
    'feedhq.backends.RateLimitMultiBackend',
)

TEMPLATE_LOADERS = (
    ('django.template.loaders.cached.Loader', (
        'django.template.loaders.filesystem.Loader',
        'django.template.loaders.app_directories.Loader',
    )),
)
if DEBUG:
    TEMPLATE_LOADERS = TEMPLATE_LOADERS[0][1]

TEMPLATE_CONTEXT_PROCESSORS = (
    'django.contrib.auth.context_processors.auth',
    'django.core.context_processors.debug',
    'django.core.context_processors.i18n',
    'django.core.context_processors.media',
    'django.core.context_processors.request',
    'django.contrib.messages.context_processors.messages',
    'sekizai.context_processors.sekizai',
)

parsed_redis = urlparse.urlparse(os.environ['REDIS_URL'])
path, q, querystring = parsed_redis.path.partition('?')
CACHES = {
    'default': {
        'BACKEND': 'redis_cache.RedisCache',
        'LOCATION': parsed_redis.netloc,
        'OPTIONS': {
            'DB': int(path[1:])
        },
    },
}

RQ = {
    'eager': bool(urlparse.parse_qs(querystring).get('eager', False)),
}


MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

if 'SENTRY_DSN' in os.environ:
    MIDDLEWARE_CLASSES = MIDDLEWARE_CLASSES + (
        'raven.contrib.django.middleware.Sentry404CatchMiddleware',
    )

ROOT_URLCONF = 'feedhq.urls'

TEMPLATE_DIRS = (
    os.path.join(BASE_DIR, 'templates'),
)

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'django.contrib.messages',

    'django_push.subscriber',
    'floppyforms',
    'sekizai',
    'django_rq_dashboard',

    'feedhq.feeds',
    'feedhq.profiles',

    'password_reset',
)

LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'locale'),
)

LOGIN_URL = reverse_lazy('login')
LOGIN_REDIRECT_URL = reverse_lazy('feeds:home')

DATE_FORMAT = 'M j, H:i'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(asctime)s %(levelname)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'sentry': {
            'level': 'INFO',
            'class': 'raven.contrib.django.handlers.SentryHandler',
        },
        'null': {
            'level': 'DEBUG',
            'class': 'django.utils.log.NullHandler',
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': True,
        },
        'feedupdater': {
            'handlers': ['console', 'sentry'],
            'level': 'DEBUG',
        },
        'ratelimitbackend': {
            'handlers': ['console', 'sentry'],
            'level': 'DEBUG',
        },
        'bleach': {
            'handlers': ['null'],
        },
        'raven': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'sentry.errors': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

if 'READITLATER_API_KEY' in os.environ:
    API_KEYS = {
        'readitlater': os.environ['READITLATER_API_KEY']
    }

if 'INSTAPAPER_CONSUMER_KEY' in os.environ:
    INSTAPAPER = {
        'CONSUMER_KEY': os.environ['INSTAPAPER_CONSUMER_KEY'],
        'CONSUMER_SECRET': os.environ['INSTAPAPER_CONSUMER_SECRET'],
    }

if 'READABILITY_CONSUMER_KEY' in os.environ:
    READABILITY = {
        'CONSUMER_KEY': os.environ['READABILITY_CONSUMER_KEY'],
        'CONSUMER_SECRET': os.environ['READABILITY_CONSUMER_SECRET'],
    }

try:
    import debug_toolbar  # noqa
except ImportError:
    pass
else:
    INTERNAL_IPS = (
        '127.0.0.1',
    )

    INSTALLED_APPS += (
        'debug_toolbar',
    )

    MIDDLEWARE_CLASSES += (
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    )

    DEBUG_TOOLBAR_CONFIG = {
        'INTERCEPT_REDIRECTS': False,
        'HIDE_DJANGO_SQL': False,
    }

    DEBUG_TOOLBAR_PANELS = (
        'debug_toolbar.panels.version.VersionDebugPanel',
        'debug_toolbar.panels.timer.TimerDebugPanel',
        'debug_toolbar.panels.settings_vars.SettingsVarsDebugPanel',
        'debug_toolbar.panels.headers.HeaderDebugPanel',
        'debug_toolbar.panels.request_vars.RequestVarsDebugPanel',
        'debug_toolbar.panels.template.TemplateDebugPanel',
        'debug_toolbar.panels.sql.SQLDebugPanel',
        'debug_toolbar.panels.signals.SignalDebugPanel',
        'debug_toolbar.panels.logger.LoggingPanel',
    )
