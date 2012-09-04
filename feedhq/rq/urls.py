from django.conf.urls import url, patterns

from . import views


urlpatterns = patterns('',
    url(r'^$', views.stats, name='rq_stats'),
    url(r'^queues/(?P<queue>.+)/$', views.queue, name='rq_queue'),
    url(r'^workers/(?P<worker>.+)/$', views.worker, name='rq_worker'),
    url(r'^jobs/(?P<job>.+)/$', views.job, name='rq_job'),
)
