from django.conf.urls import url, patterns, include

from . import views

urlpatterns = patterns(
    '',
    url(r'^profile/$', views.profile, name='profile'),
    url(r'^export/$', views.export, name='export'),
    url(r'^readlater/(?P<service>readability|readitlater|instapaper|none)/$',
        views.services, name='services'),
    url(r'^destroy/$', views.destroy, name='destroy_account'),
    url(r'^destroy/done/$', views.destroy_done, name='destroy_done'),
    url(r'^recover/$', views.recover, name='password_reset_recover'),
    url(r'^', include('password_reset.urls')),
)
