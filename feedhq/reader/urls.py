from django.conf.urls import include, url

from . import views


urlpatterns = [
    url(r'^accounts/ClientLogin$', views.login, name='login'),
    url(r'^reader/api/0/', include('feedhq.reader.api_urls')),
    url(r'^reader/atom/(?P<content_id>.+)?$', views.stream_contents,
        {'output': 'atom'}, name='atom_contents'),
]
