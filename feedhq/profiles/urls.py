from django.conf.urls.defaults import url, patterns

from . import views

urlpatterns = patterns('',
    url(r'^profile/$', views.profile, name='profile'),
)
