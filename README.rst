FeedHQ
======

.. image:: https://travis-ci.org/feedhq/feedhq.png?branch=master
   :alt: Build Status
   :target: https://travis-ci.org/feedhq/feedhq

FeedHQ is a simple, lightweight web-based feed reader. Main features:

User-facing features
--------------------

* RSS and ATOM support

* Grouping by categories

* Awesome pagination and intelligent browsing

* Great readability on all screen sizes (smatphones, tablets and desktops)

* Mobile-friendly, retina-ready

* Reading list management with Instapaper, Readability or Read It Later
  support

* Filter out already read entries and duplicates

* Hides images/media by default (and therefore filters ads and tracking stuff)

* Multiple user support

* Control on entries' time to live (days, weeks, months or forever)

* `OPML import`_

* Syntax highlighting, awesome for reading tech blogs

* Keyboard navigation

Developer- / Sysadmin-facing features
-------------------------------------

* Nice with web servers, uses ETag and Last-Modified HTTP headers

* Handles HTTP status codes nicely (permanent redirects, gone, not-modified…)

* Exponential backoff support

* `PubSubHubbub`_ support

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

    from .default_settings import *

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

Then deploy the Django app using the recipe that fits your installation. More
documentation on the `Django deployment guide`_.

.. _Django deployment guide: http://docs.djangoproject.com/en/dev/howto/deployment/

Once your application is deployed (you've run ``django-admin.py
syncdb --settings=feedhq.settings`` to create the database tables and
``django-admin.py collectstatic --settings=feedhq.settings`` to collect your
static files), you can add users to the application. On the admin interface,
add as many users as you want. Then add some some categories and feeds to
your account using the regular interface,

Crawl for updates::

    django-admin.py updatefeeds --settings=feedhq.settings

Set up a cron job to update your feeds on a regular basis. This puts the
oldest-updated feeds in the update queue::

    */5 * * * * /path/to/env/django-admin.py updatefeeds --settings=feedhq.settings

The ``updatefeeds`` command puts 1/9th of the feeds in the update queue. Feeds
won't update if they've been updated in the past 45 minutes, so the 5-minute
period for cron jobs distributes nicely the updates along the 45-minute
period.

A cron job should also be set up for picking and updating favicons (the
``--all`` switch processes existing favicons in case they have changed, which
you should probably do every month or so)::

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

    from .default_settings import *

    # Your regular settings here

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

.. _django-debug-toolbar: https://github.com/django-debug-toolbar/django-debug-toolbar

`Foreman`_ is used in development to start a lightweight Django server, run
one `RQ`_ worker and interactively preprocess changes in SCSS files to CSS
with `Compass`_. A running `Redis`_ server, Ruby, and `Bundler`_ are
prerequisites for this workflow::

    bundle install
    make run

.. _Foreman: http://ddollar.github.com/foreman/
.. _RQ: http://python-rq.org/
.. _Compass: http://compass-style.org/
.. _Redis: http://redis.io/
.. _Bundler: http://gembundler.com/

When running ``django-admin.py updatefeeds`` on your development machine,
make sure you have ``DEBUG = True`` in your settings to avoid making
PubSubHubbub subscription requests without any valid callback URL.
