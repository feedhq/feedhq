# -*- coding: utf-8 -*-
import json

from collections import defaultdict

from django.conf import settings
from django.contrib.auth.views import logout as do_logout
from django.core.exceptions import PermissionDenied
from django.http import (HttpResponse, HttpResponsePermanentRedirect,
                         HttpResponseNotAllowed)
from django.utils.crypto import constant_time_compare
from rq import Worker

from .feeds.models import Feed, UniqueFeed
from .profiles.models import User
from .utils import get_redis_connection


robots = lambda _: HttpResponse('User-agent: *\nDisallow:\n',
                                content_type='text/plain')

humans = lambda _: HttpResponse(u"""/* TEAM */
    Main developer: Bruno Renié
    Contact: contact [at] feedhq.org
    Twitter: @brutasse, @FeedHQ
    From: Switzerland

/* SITE */
    Language: English
    Backend: Django, PostgreSQL, elasticsearch, Redis
    Frontend: SCSS, Compass, Iconic
""", content_type='text/plain; charset=UTF-8')

favicon = lambda _: HttpResponsePermanentRedirect(
    '%score/img/icon-rss.png' % settings.STATIC_URL
)

touch_icon = lambda _: HttpResponsePermanentRedirect(
    '%sfeeds/img/touch-icon-114.png' % settings.STATIC_URL
)


def logout(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(["POST"], "Logout via POST only")
    return do_logout(request)


def health(request):
    secret = settings.HEALTH_SECRET
    if secret is not None and not request.user.is_superuser:
        token = request.META.get('HTTP_X_TOKEN', None)
        if token is None or not constant_time_compare(token, secret):
            raise PermissionDenied()
    conn = get_redis_connection()
    workers = Worker.all(connection=conn)

    queues = defaultdict(lambda: defaultdict(int))
    for worker in workers:
        for queue in worker.queues:
            queues[queue.name]['workers'] += 1
            queues[queue.name]['tasks'] = queue.count

    data = {
        'queues': queues,
        'users': {
            'total': User.objects.all().count(),
            'active': User.objects.filter(is_suspended=False).count(),
        },
        'feeds': {
            'total': Feed.objects.all().count(),
            'unique': UniqueFeed.objects.all().count(),
        },
    }
    response = HttpResponse(json.dumps(data))
    response['Content-Type'] = 'application/json'
    return response
