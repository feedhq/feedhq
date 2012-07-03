# -*- coding: utf-8 -*-
from django.conf import settings
from django.conf.urls import url, patterns, include
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import HttpResponse, HttpResponsePermanentRedirect

from ratelimitbackend import admin
admin.autodiscover()

# This patches User and needs to be done early
from .profiles.models import User, DjangoUser  # noqa

from .profiles.forms import AuthForm

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
    '%sfeeds/img/icon-rss.png' % settings.STATIC_URL
)

touch_icon = lambda _: HttpResponsePermanentRedirect(
    '%sfeeds/img/touch-icon-114.png' % settings.STATIC_URL
)

urlpatterns = patterns('',
    (r'^admin/rq/', include('feedhq.rq.urls')),
    (r'^admin/', include(admin.site.urls)),
    (r'^subscriber/', include('django_push.subscriber.urls')),
    url(r'^robots.txt$', robots),
    url(r'^humans.txt$', humans),
    url(r'^favicon.ico$', favicon),
    url(r'^apple-touch-icon-precomposed.png$', touch_icon),
    (r'^accounts/', include('feedhq.profiles.urls')),
    (r'^', include('feedhq.feeds.urls', namespace='feeds')),
)

urlpatterns += patterns('ratelimitbackend.views',
    url(r'^login/$', 'login', {'authentication_form': AuthForm}, name='login'),
)

urlpatterns += patterns('django.contrib.auth.views',
    url(r'^logout/$', 'logout', name='logout'),
)

urlpatterns += staticfiles_urlpatterns()
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
