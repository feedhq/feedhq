from django.conf.urls.defaults import url, patterns

from . import views

urlpatterns = patterns('',
    url(r'^profile/$', views.profile, name='profile'),
    url(r'^export/$', views.export, name='export'),
    url(r'^readlater/(?P<service>readability|readitlater|instapaper|none)/$',
        views.services, name='services'),
    url(r'^recover/$', views.recover, name='recover'),
    url(r'^recover/done/$', views.recover_done, name='recover_done'),
    url(r'^recover/(?P<key>.+)/$', views.reset, name='reset'),
)
