FeedHQ
======

.. image:: https://travis-ci.org/feedhq/feedhq.png?branch=master
   :alt: Build Status
   :target: https://travis-ci.org/feedhq/feedhq

.. image:: https://coveralls.io/repos/feedhq/feedhq/badge.png?branch=master
   :alt: Coverage Status
   :target: https://coveralls.io/r/feedhq/feedhq?branch=master

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

* Filter out already read entries

* Hides images/media by default (and therefore filters ads and tracking stuff)

* Multiple user support

* `OPML import`_

* Syntax highlighting, awesome for reading tech blogs

* Keyboard navigation

* `Subtome`_ support

Developer- / Sysadmin-facing features
-------------------------------------

* Nice with web servers, uses ETag and Last-Modified HTTP headers

* Handles HTTP status codes nicely (permanent redirects, gone, not-modified…)

* Exponential backoff support

* `PubSubHubbub`_ support

.. _PubSubHubbub: http://code.google.com/p/pubsubhubbub/

.. _OPML import: http://www.opml.org/

.. _Subtome: https://www.subtome.com/

Installation
------------

Requirements:

* Python 2.7
* Redis (2.6+ recommended)
* PostgreSQL (9.2+ recommended but anything >= 8.4 should work)

Getting the code::

    git clone https://github.com/feedhq/feedhq.git
    cd feedhq
    virtualenv -p python2 env
    source env/bin/activate
    add2virtualenv .
    pip install -r requirements.txt

Configuration
-------------

FeedHQ relies on environment variables for its configuration. The required
environment variables are:

* ``DJANGO_SETTINGS_MODULE``: set it to ``feedhq.settings``.
* ``SECRET_KEY``: set to a long random string.
* ``ALLOWED_HOSTS``: space-separated list of hosts which serve the web app.
  E.g. ``www.feedhq.org feedhq.org``.
* ``FROM_EMAIL``: the email address that sends automated emails (password
  lost, etc.). E.g. ``FeedHQ <feedhq@example.com>``.
* ``REDIS_URL``: a URL for configuring redis. E.g.
  ``redis://localhost:6354/1``.
* ``DATABASE_URL``: a heroku-like database URL. E.g.
  ``postgres://user:password@host:port/database``.

Optionally you can customize:

* ``DEBUG``: set it to a non-empty value to enable the Django debug mode.
* ``MEDIA_ROOT``: the absolute location where media files (user-generated) are
  stored. This must be a public directory on your webserver available under
  ``MEDIA_URL``.
* ``MEDIA_URL``: the URL that handles media files (user-generated) served from
  ``MEDIA_ROOT``. By default, it is set to ``/media/``.
* ``STATIC_ROOT``: the absolute location where static files (CSS/JS files) are
  stored. This must be a public directory on your webserver available under
  the ``/static/`` URL.
* ``STATIC_URL``: the URL that serves static files (CSS/JS files) located in
  ``STATIC_ROOT``. By default, it is set to ``/static/``.
* ``SENTRY_DSN``: a DSN to enable `Sentry`_ debugging.
* ``SESSION_COOKIE_PATH``: the path set on the session cookie. E.g., ``/``.
* ``HTTPS``: set-it to a non-empty value to configure FeedHQ for SSL access.
* ``EMAIL_URL``: a URL for configuring email. E.g.
  ``smtp://user:password@host:port/?backend=my.EmailBackend&use_tls=true``.
  The ``backend`` querystring parameter sets the Django ``EMAIL_BACKEND``
  setting. By default emails only go to the development console.

.. _Sentry: https://www.getsentry.com/

For integration with external services:

* ``READITLATER_API_KEY``: your `Pocket`_ API key.
* ``INSTAPAPER_CONSUMER_KEY``, ``INSTAPAPER_CONSUMER_SECRET``: your
  `Instapaper`_ API keys.
* ``READABILITY_CONSUMER_KEY``, ``READABILITY_CONSUMER_SECRET``: your
  `Readability`_ API keys.

.. _Pocket: http://getpocket.com/
.. _Instapaper: http://www.instapaper.com/
.. _Readability: https://www.readability.com/

Then deploy the Django app using the recipe that fits your installation. More
documentation on the `Django deployment guide`_. The WSGI application is
located at ``feedhq.wsgi.application``.

.. _Django deployment guide: http://docs.djangoproject.com/en/dev/howto/deployment/

Note that additionally to the web server, you need to run one or more
consumers for the task queue. This is done with the ``rqworker`` management
command::

    django-admin.py rqworker store high default favicons

The arguments are queue names.

Once your application is deployed (you've run ``django-admin.py syncdb`` to
create the database tables, ``django-admin.py migrate`` to run the initial
migrations and ``django-admin.py collectstatic`` to collect your static
files), you can add users to the application. On the admin interface, add
as many users as you want. Then add some some categories and feeds to your
account using the regular interface.

Crawl for updates::

    django-admin.py sync_scheduler
    django-admin.py updatefeeds

Set up a cron job to update your feeds on a regular basis. This puts the
oldest-updated feeds in the update queue::

    */5 * * * * /path/to/env/django-admin.py updatefeeds

The ``updatefeeds`` command puts 1/12th of the feeds in the update queue. Feeds
won't update if they've been updated in the past 60 minutes, so the 5-minute
period for cron jobs distributes nicely the updates along the 1-hour
period.

A cron job should also be set up for picking and updating favicons (the
``--all`` switch processes existing favicons in case they have changed, which
you should probably do every month or so)::

    @monthly /path/to/env/bin/django-admin.py favicons --all

Here is a full list of management commands that you should schedule:

* ``add_missing`` creates the missing denormalized URLs for crawling. Since
  URLs are denormalized it's recommended to run it every now and then to
  ensure consistency.

  Recommended frequency: hourly.

  Resource consumption: negligible (2 database queries).

* ``delete_unsubscribed`` is the delete counterpart of ``add_missing``.

  Recommended frequency: hourly.

  Resource consumption: negligible (2 database queries).

* ``favicons --all`` forces fetching the favicons for all existing URLs. It's
  useful for picking up new favicons when they're updated. Depending on your
  volume of data, this can be resource-intensive.

  Recommended frequency: monthly.

  Resource consumption: the command itself only triggers async jobs but the
  jobs perform network I/O, HTML parsing, disk I/O and database queries.

* ``updatefeeds`` picks 1/12th of the URLs and fetches them.

  Recommended frequency: every 5 minutes.

  Resource consumption: the command itself only triggers async jobs but the
  jobs perform network I/O, HTML parsing and -- when updates are found --
  database queries.

* ``sync_scheduler`` adds missing URLs to the scheduler. Also useful to run
  every now and then.

  Recommended frequency: every hour.

  Resource consumption: one large database query per chunk of 10k feeds which
  aren't in the scheduler, plus one redis ``HMSET`` per URL that's not in the
  scheduler. As a routine task it's not resource-intensive.

* ``backup_scheduler`` puts all the scheduler data back to the database. This
  is useful as a maintenance job for your backups as the scheduler can be
  up-to-date more quickly on a database restore.

  Recommended frequency: 2 to 4 times a day.

  Resource consumption: intensive. One database ``UPDATE`` per URL that's in
  the scheduler.

* ``sync_pubssubhubbub`` unsubscribes from unneeded PubSubHubbub
  subscriptions.

  Recommended frequency: once a day.

  Resource consumption: low.

* ``clean_rq`` removes stale RQ jobs.

  Recommended frequency: once a day.

  Resource consumption: low. Only makes requests to Redis.

* ``delete_old`` removes expired entries as determined by each user's entry TTL.

  Recommended frequency: once a day.

  Resource consumption: medium, makes ``DELETE`` queries to postgres (1 per
  user).

Development
-----------

Install the development requirements::

    pip install -r requirements-dev.txt

Run the tests::

    make test

Or if you want to run the tests with ``django-admin.py`` directly, make sure
you use ``feedhq.test_settings`` as the ``DJANGO_SETTINGS_MODULE`` environment
variable to avoid making network calls while running the tests.

The Django debug toolbar is enabled when the ``DEBUG`` environment variable is
true and the ``django-debug-toolbar`` package is installed.

`Foreman`_ is used in development to start a lightweight Django server, run
one `RQ`_ worker and interactively preprocess changes in SCSS files to CSS
with `Compass`_. Environment variables are managed using a `python port`_ of
Daemontools' ``envdir`` utility. A running `Redis`_ server, Ruby and
`Bundler`_ are prerequisites for this workflow::

    bundle install
    make run

.. _Foreman: http://ddollar.github.com/foreman/
.. _RQ: http://python-rq.org/
.. _Compass: http://compass-style.org/
.. _Redis: http://redis.io/
.. _Bundler: http://gembundler.com/
.. _Daemontools: http://cr.yp.to/daemontools.html
.. _python port: https://pypi.python.org/pypi/envdir

When running ``django-admin.py updatefeeds`` on your development machine,
make sure you have the ``DEBUG`` environment variable present to avoid making
PubSubHubbub subscription requests without any valid callback URL.

Environment variables for development are set in the ``envdir`` directory. For
tests, they are located in the ``tests/envdir`` directory.
