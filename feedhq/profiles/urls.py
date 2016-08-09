from django.conf.urls import include, url

from . import views

urlpatterns = [
    url(r'^stats/$', views.stats, name='stats'),
    url(r'^profile/$', views.profile, name='profile'),
    url(r'^sharing/$', views.sharing, name='sharing'),
    url(r'^bookmarklet/$', views.bookmarklet, name='bookmarklet'),
    url(r'^password/$', views.password, name='password'),
    url(r'^export/$', views.export, name='export'),
    url(r'^readlater/(?P<service>readability|readitlater|instapaper|'
        r'pocket|wallabag|none)/$',
        views.services, name='services'),
    url(r'^readlater/pocket/return/$', views.pocket, name='pocket_return'),
    url(r'^readlater/$', views.read_later, name='read_later'),
    url(r'^destroy/$', views.destroy, name='destroy_account'),
    url(r'^destroy/sent/$', views.destroy_sent, name='destroy_sent'),
    url(r'^destroy/confirm/(?P<token>[^\/]+)/$',
        views.destroy_confirm, name='destroy_confirm'),
    url(r'^destroy/done/$', views.destroy_done, name='destroy_done'),
    url(r'^recover/$', views.recover, name='password_reset_recover'),
    url(r'^', include('password_reset.urls')),
]
