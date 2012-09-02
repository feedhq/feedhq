FeedHQ
======

.. image:: https://secure.travis-ci.org/feedhq/feedhq.png
   :alt: Build Status
   :target: https://secure.travis-ci.org/feedhq/feedhq

FeedHQ is a simple, lightweight web-based feed reader. Main features:

* RSS and ATOM support

* Grouping by categories

* Awesome pagination and intelligent browsing

* Built with readability in mind

* Mobile-friendly, retina-ready

* Reading list management with Instapaper, Readability or Read It Later
  support

* Filter out already read entries

* Control on entries' time to live (days, weeks, months or forever)

* Nice with web servers, uses ETag and Last-Modified HTTP headers

* Handles HTTP status codes nicely (permanent redirects, gone, not-modified…)

* Exponential backoff support

* Hides images by default (and therefore filters ads and tracking stuff)

* Multiple user support

* `PubSubHubbub`_ support

* `OPML import`_

* Syntax highlighting, awesome for reading tech blogs

* Keyboard navigation

.. _PubSubHubbub: http://code.google.com/p/pubsubhubbub/

.. _OPML import: http://www.opml.org/

Installation
------------

Getting the code::

    git clone git@github.com:feedhq/feedhq.git
    cd feedhq
    virtualenv -p python2 env
    source env/bin/activate
    add2virtualenv .
    pip install -r requirements.txt

Configuration
-------------

Create ``feedhq/settings.py`` and put the minimal stuff in it::

    from default_settings import *

    ADMINS = (
        ('Your name', 'email@example.com'),
    )
    MANAGERS = ADMINS

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql_psycopg2',
            'NAME': 'feedhq',
            'USER': 'postgres',
        },
    }

    SECRET_KEY = 'something secret'

    # For development, don't do cache-busting
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

    TIME_ZONE = 'Europe/Paris'

    EMAIL_HOST = 'mail.your_domain.com'
    EMAIL_SUBJECT_PREFIX = '[FeedHQ] '

For Readability, Instapaper and Pocket support, you'll need a couple of
additional settings::

    API_KEYS = {
        'readitlater': 'your readitlater (pocket) key',
    }

    INSTAPAPER = {
        'CONSUMER_KEY': 'yay isntappaper',
        'CONSUMER_SECRET': 'secret',
    }

    READABILITY = {
        'CONSUMER_KEY': 'yay readability',
        'CONSUMER_SECRET': 'othersecret',
    }

Then deploy the Django app using the recipe that fits your installation (with
mod_wsgi or mod_fcgi). More documentation on the `Django deployment guide`_.

.. _Django deployment guide: http://docs.djangoproject.com/en/dev/howto/deployment/

Once your application is deployed (you've run
``django-admin.py syncdb --settings=feedhq.settings`` to create the database
tables), you can add users to the application. On the admin interface, add as
many users as you want. When you've added some categories and feeds to your
account, you can crawl for updates::

    django-admin.py updatefeeds --settings=feedhq.settings

Set up a cron job to update your feeds on a regular basis. This puts the
last-updated feeds in the update queue::

    */5 * * * * /path/to/env/django-admin.py updatefeeds --settings=feedhq.settings

A cron job should also be set up for picking and updating favicons (the
``--all`` switch processes existing favicons in case they have changed)::

    @daily /path/to/env/bin/django-admin.py favicons --settings=feedhq.settings
    @monthly /path/to/env/bin/django-admin.py favicons --all --settings=feedhq.settings

And a final one to purge expired sessions from the DB::

    @daily /path/to/env/bin/django-admin.py cleanup --settings=feedhq.settings

Development
-----------

Install the development requirements::

    pip install -r requirements-dev.txt

Run the tests::

    make test

Or if you want to run the tests with ``django-admin.py`` directly, make sure
you use ``feedhq.test_settings`` to avoid making network calls while running
the tests.

If you want to contribute and need an environment more suited for development,
you can use the ``settings.py`` file to alter default settings. For example,
to enable the `django-debug-toolbar`_::

    MIDDLEWARE_CLASSES += (
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    )

    INTERNAL_IPS = ('127.0.0.1',)

    INSTALLED_APPS += (
        'debug_toolbar',
    )

    DEBUG_TOOLBAR_CONFIG = {
        'INTERCEPT_REDIRECTS': False,
        'HIDE_DJANGO_SQL': False,
    }

.. _django-debug-toolbar: https://github.com/robhudson/django-debug-toolbar

When running ``django-admin.py updatefeeds`` on your development machine,
make sure you have ``DEBUG = True`` in your settings to avoid making
PubSubHubbub subscription requests without any valid callback URL.
