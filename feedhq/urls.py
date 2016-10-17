# -*- coding: utf-8 -*-
from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from ratelimitbackend import admin
from ratelimitbackend.views import login

from . import views
from .profiles.forms import AuthForm

admin.autodiscover()

urlpatterns = [
    url(r'^admin/rq/', include('django_rq_dashboard.urls')),
    url(r'^admin/', admin.site.urls),
    url(r'^subscriber/', include('django_push.subscriber.urls')),
    url(r'^health/$', views.health, name='health'),
    url(r'^robots.txt$', views.robots),
    url(r'^humans.txt$', views.humans),
    url(r'^favicon.ico$', views.favicon),
    url(r'^apple-touch-icon-precomposed.png$', views.touch_icon),
    url(r'^apple-touch-icon.png$', views.touch_icon),
    url(r'^', include(('feedhq.reader.urls', 'reader'), namespace='reader')),
    url(r'^accounts/', include('feedhq.profiles.urls')),
    url(r'^', include(('feedhq.feeds.urls', 'feeds'), namespace='feeds')),
    url(r'^login/$', login, {'authentication_form': AuthForm}, name='login'),
    url(r'^logout/$', views.logout, name='logout'),
]

urlpatterns += staticfiles_urlpatterns()
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
