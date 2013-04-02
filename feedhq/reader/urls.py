from django.conf.urls import patterns, url, include

from . import views


urlpatterns = patterns(
    '',
    url(r'^accounts/ClientLogin$', views.login, name='login'),
    url(r'^reader/api/0/', include('feedhq.reader.api_urls')),
)
