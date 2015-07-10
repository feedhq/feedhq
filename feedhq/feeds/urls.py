from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^$', views.entries_list, name='entries'),
    url(r'^(?P<page>\d+)/$', views.entries_list, name='entries'),
    url(r'^(?P<mode>unread|stars)/$', views.entries_list, name='entries'),
    url(r'^(?P<mode>unread|stars)/(?P<page>\d+)/$',
        views.entries_list, name='entries'),

    url(r'^dashboard/$', views.dashboard, name='dashboard'),
    url(r'^dashboard/(?P<mode>unread|stars)/$', views.dashboard,
        name='dashboard'),

    url(r'^manage/$', views.manage, name='manage'),

    url(r'^import/$', views.import_feeds, name='import_feeds'),
    url(r'^subscribe/$', views.subscribe, name='subscribe'),
    url(r'^keyboard/$', views.keyboard, name='keyboard'),

    # Categories
    url(r'^category/add/$', views.add_category, name='add_category'),
    url(r'^category/(?P<slug>[\w_-]+)/edit/$', views.edit_category,
        name='edit_category'),
    url(r'^category/(?P<slug>[\w_-]+)/delete/$', views.delete_category,
        name='delete_category'),

    url(r'^category/(?P<category>[\w_-]+)/$',
        views.entries_list, name='category'),
    url(r'^category/(?P<category>[\w_-]+)/(?P<page>\d+)/$',
        views.entries_list, name='category'),
    url(r'^category/(?P<category>[\w_-]+)/(?P<mode>unread|stars)/$',
        views.entries_list, name='category'),
    url(r'^category/(?P<category>[\w_-]+)/(?P<mode>unread|stars)/'
        r'(?P<page>\d+)/$', views.entries_list, name='category'),

    # Feeds
    url(r'^feed/add/$', views.add_feed, name='add_feed'),
    url(r'^feed/(?P<feed>\d+)/edit/$', views.edit_feed, name='edit_feed'),
    url(r'^feed/(?P<feed>\d+)/delete/$', views.delete_feed,
        name='delete_feed'),

    url(r'^feed/(?P<feed>\d+)/$', views.entries_list, name='feed'),
    url(r'^feed/(?P<feed>\d+)/(?P<page>\d+)/$',
        views.entries_list, name='feed'),
    url(r'^feed/(?P<feed>\d+)/(?P<mode>unread|stars)/$',
        views.entries_list, name='feed'),
    url(r'^feed/(?P<feed>\d+)/(?P<mode>unread|stars)/(?P<page>\d+)/$',
        views.entries_list, name='feed'),

    # Entries
    url(r'^entries/(?P<entry_id>\d+)/$', views.item, name='item'),
]
