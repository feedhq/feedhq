# -*- coding: utf-8 -*-
import json

from django.conf import settings
from django.contrib.auth.views import logout as do_logout
from django.http import (HttpResponse, HttpResponsePermanentRedirect,
                         HttpResponseNotAllowed)

from . import __version__

robots = lambda _: HttpResponse('User-agent: *\nDisallow:\n',
                                mimetype='text/plain')

humans = lambda _: HttpResponse(u"""/* TEAM */
    Main developer: Bruno Renié
    Contact: contact [at] feedhq.org
    Twitter: @brutasse, @FeedHQ
    From: Switzerland

/* SITE */
    Language: English
    Backend: Django, PostgreSQL, Redis
    Frontend: SCSS, Compass, Iconic
""", mimetype='text/plain; charset=UTF-8')

favicon = lambda _: HttpResponsePermanentRedirect(
    '%score/img/icon-rss.png' % settings.STATIC_URL
)

touch_icon = lambda _: HttpResponsePermanentRedirect(
    '%sfeeds/img/touch-icon-114.png' % settings.STATIC_URL
)


def manifest_webapp(request):
    manifest = {
        "version": __version__,
        "name": "FeedHQ",
        "description": "FeedHQ is a web-based feed reader",
        "launch_path": "/",
        "icons": {
            "144": '%score/img/touch-icon-144.png' % settings.STATIC_URL,
        },
        "developer": {
            "name": "Bruno Renie",
            "url": "https://feedhq.org/"
        },
        "installs_allowed_from": ["*"],
        "default_locale": "en",
        "chrome": {
            "navigation": True,
        }
    }
    return HttpResponse(json.dumps(manifest),
                        mimetype='application/x-web-app-manifest+json')


def logout(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(["POST"], "Logout via POST only")
    return do_logout(request)
