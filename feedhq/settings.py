import os

import dj_database_url
from django.core.urlresolvers import reverse_lazy
from six.moves.urllib import parse as urlparse

BASE_DIR = os.path.dirname(__file__)

DEBUG = bool(int(os.environ.get('DEBUG', 0)))

# Are we running the tests or a real server?
TESTS = False

ADMINS = MANAGERS = ()

DATABASES = {
    'default': dj_database_url.config(
        default='postgres://postgres@localhost:5432/feedhq',
    ),
}

ES_NODES = os.environ.get('ES_NODES', 'localhost:9200').split()
ES_INDEX = os.environ.get('ES_INDEX', 'feedhq')
# Aliases are created for each user for easy filtering / data isolation.
# Alias template is .format()'ed with the user id as argument.
ES_ALIAS_TEMPLATE = os.environ.get('ES_ALIAS_TEMPLATE', 'feedhq-{0}')
# Shards can only be set at index creation time.
# Over-allocate for future *node* growth.
ES_SHARDS = int(os.environ.get('ES_SHARDS', 5))
# Replicas can be changed at any time.
ES_REPLICAS = int(os.environ.get('ES_REPLICAS', 1))

TIME_ZONE = 'UTC'

LANGUAGE_CODE = 'en-us'

USE_I18N = True
USE_L10N = True
USE_TZ = True

SITE_ID = 1

MEDIA_ROOT = os.environ.get('MEDIA_ROOT', os.path.join(BASE_DIR, 'media'))
MEDIA_URL = os.environ.get('MEDIA_URL', '/media/')

STATIC_ROOT = os.environ.get('STATIC_ROOT', os.path.join(BASE_DIR, 'static'))
STATIC_URL = os.environ.get('STATIC_URL', '/static/')

SECRET_KEY = os.environ['SECRET_KEY']

# Shared secret if you want to protect the health endpoint
HEALTH_SECRET = os.environ.get('HEALTH_SECRET', None)

ALLOWED_HOSTS = os.environ['ALLOWED_HOSTS'].split()
PUSH_DOMAIN = ALLOWED_HOSTS[0]

WSGI_APPLICATION = 'feedhq.wsgi.application'

if not DEBUG:
    STATICFILES_STORAGE = ('django.contrib.staticfiles.storage.'
                           'CachedStaticFilesStorage')


def parse_email_url():
    parsed = urlparse.urlparse(os.environ['EMAIL_URL'])
    if '?' in parsed.path:
        querystring = urlparse.parse_qs(parsed.path.split('?', 1)[1])
    elif parsed.query:
        querystring = urlparse.parse_qs(parsed.query)
    else:
        querystring = {}
    if querystring:
        for key in querystring.keys():
            querystring[key] = querystring[key][0]
    if '@' in parsed.netloc:
        creds, at, netloc = parsed.netloc.partition('@')
        username, colon, password = creds.partition(':')
        host, colon, port = netloc.partition(':')
    else:
        username = password = None
        host, colon, port = parsed.netloc.partition(':')
    # Django defaults
    config = {
        'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
        'HOST': 'localhost',
        'USER': '',
        'PASSWORD': '',
        'PORT': 25,
        'SUBJECT_PREFIX': '[FeedHQ] ',
        'USE_TLS': False,
    }
    if host:
        config['HOST'] = host
    if username:
        config['USER'] = username
    if password:
        config['PASSWORD'] = password
    if port:
        config['PORT'] = int(port)
    if 'subject_prefix' in querystring:
        config['SUBJECT_PREFIX'] = querystring['subject_prefix'][0]
    if 'backend' in querystring:
        config['BACKEND'] = querystring['backend']
    if 'use_tls' in querystring:
        config['USE_TLS'] = True
    return config


DEFAULT_FROM_EMAIL = SERVER_EMAIL = os.environ['FROM_EMAIL']

if 'EMAIL_URL' in os.environ:
    email_config = parse_email_url()
    EMAIL_BACKEND = email_config['BACKEND']
    EMAIL_HOST = email_config['HOST']
    EMAIL_HOST_PASSWORD = email_config['PASSWORD']
    EMAIL_HOST_USER = email_config['USER']
    EMAIL_PORT = email_config['PORT']
    EMAIL_SUBJECT_PREFIX = email_config.get('SUBJECT_PREFIX', '[FeedHQ] ')
    EMAIL_USE_TLS = email_config['USE_TLS']
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

AUTHENTICATION_BACKENDS = (
    'feedhq.backends.RateLimitMultiBackend',
)

AUTH_USER_MODEL = 'profiles.User'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [os.path.join(BASE_DIR, 'templates')],
    'OPTIONS': {
        'loaders': (
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ),
        'context_processors': (
            'django.contrib.auth.context_processors.auth',
            'django.template.context_processors.debug',
            'django.template.context_processors.i18n',
            'django.template.context_processors.media',
            'django.template.context_processors.request',
            'django.contrib.messages.context_processors.messages',
            'sekizai.context_processors.sekizai',
        ),
        'builtins': [
            'django.templatetags.i18n',
            'django.templatetags.tz',
        ],
    },
}]

if not DEBUG:
    TEMPLATES[0]['OPTIONS']['loaders'] = (
        ('django.template.loaders.cached.Loader',
         TEMPLATES[0]['OPTIONS']['loaders']),
    )


def parse_redis_url():
    config = {
        'host': 'localhost',
        'port': 6379,
        'password': None,
        'db': 0,
    }
    parsed_redis = urlparse.urlparse(os.environ['REDIS_URL'])
    if '?' in parsed_redis.path and not parsed_redis.query:
        # Bug in python 2.7.3, fixed in 2.7.4
        path, q, querystring = parsed_redis.path.partition('?')
    else:
        path, q, querystring = parsed_redis.path, None, parsed_redis.query  # noqa

    querystring = urlparse.parse_qs(querystring)
    for key in querystring.keys():
        querystring[key] = querystring[key][0]
    for key in config.keys():
        querystring.pop(key, None)

    if parsed_redis.netloc.endswith('unix'):
        del config['port']
        del config['host']
        # the last item of the path could also be just part of the socket path
        try:
            config['db'] = int(os.path.split(path)[-1])
        except ValueError:
            pass
        else:
            path = os.path.join(*os.path.split(path)[:-1])
        config['unix_socket_path'] = path
        if parsed_redis.password:
            config['password'] = parsed_redis.password
    else:
        if path[1:]:
            config['db'] = int(path[1:])
        if parsed_redis.password:
            config['password'] = parsed_redis.password
        if parsed_redis.port:
            config['port'] = int(parsed_redis.port)
        if parsed_redis.hostname:
            config['host'] = parsed_redis.hostname

    return config, True if 'eager' in querystring else False


REDIS, RQ_EAGER = parse_redis_url()
# django-rq-dashboard needs an RQ setting
RQ = REDIS
location = REDIS.get('unix_socket_path', '{host}:{port}'.format(**REDIS))

CACHES = {
    'default': {
        'BACKEND': 'redis_cache.RedisCache',
        'LOCATION': location,
        'OPTIONS': {
            'DB': REDIS['db'],
            'PASSWORD': REDIS['password'],
            'PARSER_CLASS': 'redis.connection.HiredisParser',
            'PICKLE_VERSION': int(os.environ.get('CACHE_PICKLE_PROTOCOL', -1)),
        },
    },
}

MESSAGE_STORAGE = 'django.contrib.messages.storage.fallback.FallbackStorage'
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'

MIDDLEWARE = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.locale.LocaleMiddleware',
)

ROOT_URLCONF = 'feedhq.urls'

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

    'feedhq.core',
    'feedhq.profiles',
    'feedhq.feeds',
    'feedhq.reader',

    'password_reset',
)

if 'SENTRY_DSN' in os.environ:
    INSTALLED_APPS += (
        'raven.contrib.django',
    )

LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'locale'),
)

LOGIN_URL = reverse_lazy('login')
LOGIN_REDIRECT_URL = reverse_lazy('feeds:entries')

LOGGING_CONFIG = None
# Log to syslog, otherwise stdout
LOG_SYSLOG = bool(int(os.environ.get('LOG_SYSLOG', 0)))
SILENCED_LOGGERS = [
    'django.template',  # failed variable lookup, safe (expected)
    'django.server',  # access logs, available upstream (nginx/apache)
    'django.request',
    'django.db.backends',  # SQL requests
    'elasticsearch',  # too verbose
    'requests.packages.urllib3.connectionpool',  # too verbose
    'bleach',
]

REST_FRAMEWORK = {
    "URL_FORMAT_OVERRIDE": "output",
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

if 'POCKET_CONSUMER_KEY' in os.environ:
    POCKET_CONSUMER_KEY = os.environ['POCKET_CONSUMER_KEY']

SESSION_COOKIE_HTTPONLY = True

SESSION_COOKIE_PATH = os.environ.get('SESSION_COOKIE_PATH', '/')

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTOCOL', 'https')

if 'HTTPS' in os.environ:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    PUSH_SSL_CALLBACK = True

try:
    import debug_toolbar  # noqa
except ImportError:
    pass
else:
    INSTALLED_APPS += (
        'debug_toolbar',
        'elastic_panel',
    )
    MIDDLEWARE += (
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    )
    DEBUG_TOOLBAR_PANELS = [
        'debug_toolbar.panels.versions.VersionsPanel',
        'debug_toolbar.panels.timer.TimerPanel',
        'debug_toolbar.panels.settings.SettingsPanel',
        'debug_toolbar.panels.headers.HeadersPanel',
        'debug_toolbar.panels.request.RequestPanel',
        'debug_toolbar.panels.sql.SQLPanel',
        'elastic_panel.panel.ElasticDebugPanel',
        'debug_toolbar.panels.staticfiles.StaticFilesPanel',
        'debug_toolbar.panels.templates.TemplatesPanel',
        'debug_toolbar.panels.cache.CachePanel',
        'debug_toolbar.panels.signals.SignalsPanel',
        'debug_toolbar.panels.logging.LoggingPanel',
        'debug_toolbar.panels.redirects.RedirectsPanel',
    ]
