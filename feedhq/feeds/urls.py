from django.conf.urls import url, patterns

from . import views

urlpatterns = patterns(
    '',
    url(r'^$', views.entries_list, name='home'),
    url(r'^(?P<page>\d+)/$', views.entries_list, name='home'),
    url(r'^unread/$', views.entries_list,
        {'only_unread': True}, name='unread'),
    url(r'^unread/(?P<page>\d+)/$', views.entries_list,
        {'only_unread': True}, name='unread'),

    url(r'^dashboard/$', views.dashboard, name='dashboard'),

    url(r'^stars/$', views.entries_list,
        {'starred': True}, name='stars'),

    url(r'^stars/(?P<page>\d+)/$', views.entries_list,
        {'starred': True}, name='stars'),

    url(r'^import/$', views.import_feeds, name='import_feeds'),
    url(r'^subscribe/$', views.subscribe, name='subscribe'),

    # Categories
    url(r'^category/add/$', views.add_category, name='add_category'),
    url(r'^category/(?P<slug>[\w_-]+)/edit/$', views.edit_category,
        name='edit_category'),
    url(r'^category/(?P<slug>[\w_-]+)/delete/$', views.delete_category,
        name='delete_category'),

    url(r'^category/(?P<category>[\w_-]+)/$', views.entries_list,
        name='category'),

    url(r'^category/(?P<category>[\w_-]+)/(?P<page>\d+)/$',
        views.entries_list, name='category'),

    url(r'^category/(?P<category>[\w_-]+)/unread/$', views.entries_list,
        {'only_unread': True}, name='unread_category'),
    url(r'^category/(?P<category>[\w_-]+)/unread/(?P<page>\d+)/$',
        views.entries_list, {'only_unread': True}, name='unread_category'),

    # Feeds
    url(r'^feed/add/$', views.add_feed, name='add_feed'),
    url(r'^feed/(?P<feed>\d+)/edit/$', views.edit_feed, name='edit_feed'),
    url(r'^feed/(?P<feed>\d+)/delete/$', views.delete_feed,
        name='delete_feed'),

    url(r'^feed/(?P<feed>\d+)/$', views.entries_list, name='feed'),
    url(r'^feed/(?P<feed>\d+)/(?P<page>\d+)/$', views.entries_list,
        name='feed'),
    url(r'^feed/(?P<feed>\d+)/unread/$', views.entries_list,
        {'only_unread': True}, name='unread_feed'),
    url(r'^feed/(?P<feed>\d+)/unread/(?P<page>\d+)/$', views.entries_list,
        {'only_unread': True}, name='unread_feed'),

    # Entries
    url(r'^entries/(?P<entry_id>\d+)/$', views.item, name='item'),
)
