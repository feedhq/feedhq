import os

from django.core.wsgi import get_wsgi_application
from raven import Client
from raven.middleware import Sentry


application = get_wsgi_application()
if 'SENTRY_DSN' in os.environ:
    application = Sentry(application, Client())
