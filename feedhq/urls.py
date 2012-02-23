from django.conf import settings
from django.conf.urls.defaults import url, patterns, include
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import HttpResponse, HttpResponsePermanentRedirect

from ratelimitbackend import admin
admin.autodiscover()

robots = lambda _: HttpResponse('User-agent: *\nDisallow:\n',
                                mimetype='text/plain')
favicon = lambda _: HttpResponsePermanentRedirect(
    '%sfeeds/img/icon-rss.png' % settings.STATIC_URL
)

urlpatterns = patterns('',
    (r'^admin/', include(admin.site.urls)),
    (r'^subscriber/', include('django_push.subscriber.urls')),
    url(r'^robots.txt$', robots),
    url(r'^favicon.ico$', favicon),
    (r'^accounts/', include('feedhq.profiles.urls')),
    (r'^', include('feedhq.feeds.urls', namespace='feeds')),
)

urlpatterns += patterns('ratelimitbackend.views',
    url(r'^login/$', 'login', name='login'),
)

urlpatterns += patterns('django.contrib.auth.views',
    url(r'^logout/$', 'logout', name='logout'),
)

urlpatterns += staticfiles_urlpatterns()
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
