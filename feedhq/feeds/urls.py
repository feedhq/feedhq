from django.conf.urls import url, patterns

from . import views

urlpatterns = patterns('',
    url(r'^$', views.feed_list, name='home'),
    url(r'^(?P<page>\d+)/$', views.feed_list, name='home'),
    url(r'^unread/$', views.feed_list,
        {'only_unread': True}, name='unread'),
    url(r'^unread/(?P<page>\d+)/$', views.feed_list,
        {'only_unread': True}, name='unread'),

    url(r'^dashboard/$', views.dashboard, name='dashboard'),

    url(r'^import/$', views.import_feeds, name='import_feeds'),
    url(r'^bookmarklet/$', views.bookmarklet, name='bookmarklet'),
    url(r'^bookmarklet/js/$', views.bookmarklet_js, name='bookmarklet_js'),
    url(r'^subscribe/$', views.subscribe, name='bookmarklet_subscribe'),
    url(r'^subscribe/save/$', views.save_subscribe,
        name='bookmarklet_subscribe_save'),

    # Categories
    url(r'^category/add/$', views.add_category, name='add_category'),
    url(r'^category/(?P<slug>[\w_-]+)/edit/$', views.edit_category,
        name='edit_category'),
    url(r'^category/(?P<slug>[\w_-]+)/delete/$', views.delete_category,
        name='delete_category'),

    url(r'^category/(?P<category>[\w_-]+)/$', views.feed_list,
        name='category'),

    url(r'^category/(?P<category>[\w_-]+)/(?P<page>\d+)/$',
        views.feed_list, name='category'),

    url(r'^category/(?P<category>[\w_-]+)/unread/$', views.feed_list,
        {'only_unread': True}, name='unread_category'),
    url(r'^category/(?P<category>[\w_-]+)/unread/(?P<page>\d+)/$',
        views.feed_list, {'only_unread': True}, name='unread_category'),

    # Feeds
    url(r'^feed/add/$', views.add_feed, name='add_feed'),
    url(r'^feed/(?P<feed>\d+)/edit/$', views.edit_feed, name='edit_feed'),
    url(r'^feed/(?P<feed>\d+)/delete/$', views.delete_feed,
        name='delete_feed'),

    url(r'^feed/(?P<feed>\d+)/$', views.feed_list, name='feed'),
    url(r'^feed/(?P<feed>\d+)/(?P<page>\d+)/$', views.feed_list, name='feed'),
    url(r'^feed/(?P<feed>\d+)/unread/$', views.feed_list,
        {'only_unread': True}, name='unread_feed'),
    url(r'^feed/(?P<feed>\d+)/unread/(?P<page>\d+)/$', views.feed_list,
        {'only_unread': True}, name='unread_feed'),

    # Entries
    url(r'^entries/(?P<entry_id>\d+)/$', views.item, name='item'),
)
