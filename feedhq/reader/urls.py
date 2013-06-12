from django.conf.urls import patterns, url, include

from . import views


urlpatterns = patterns(
    '',
    url(r'^accounts/ClientLogin$', views.login, name='login'),
    url(r'^reader/api/0/', include('feedhq.reader.api_urls')),
    url(r'^reader/atom/(?P<content_id>.+)?$', views.stream_contents,
        {'output': 'atom'}, name='atom_contents'),

)
