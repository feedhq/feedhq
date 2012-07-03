import redis

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.translation import ugettext_lazy as _
from django.views import generic

from rq import Queue, Worker, get_failed_queue, use_connection
from rq.exceptions import NoSuchJobError
from rq.job import Job


def get_connection():
    opts = getattr(settings, 'RQ', {})
    opts.pop('eager', None)
    return redis.Redis(**opts)


def serialize_job(job):
    return dict(
        id=job.id,
        created_at=job.created_at,
        enqueued_at=job.enqueued_at,
        ended_at=job.ended_at,
        origin=job.origin,
        result=job._result,
        exc_info=job.exc_info,
        description=job.description,
    )


class SuperUserMixin(object):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        use_connection(redis=get_connection())
        return super(SuperUserMixin, self).dispatch(request, *args, **kwargs)


class Stats(SuperUserMixin, generic.TemplateView):
    template_name = 'rq/stats.html'

    def get_context_data(self, **kwargs):
        ctx = super(Stats, self).get_context_data(**kwargs)
        ctx.update({
            'queues': Queue.all(),
            'workers': Worker.all(),
            'title': 'RQ Status',
        })
        return ctx
stats = Stats.as_view()


class QueueDetails(SuperUserMixin, generic.TemplateView):
    template_name = 'rq/queue.html'

    def get_context_data(self, **kwargs):
        ctx = super(QueueDetails, self).get_context_data(**kwargs)
        queue = Queue(self.kwargs['queue'])
        ctx.update({
            'queue': queue,
            'jobs': [serialize_job(job) for job in queue.jobs],
            'title': "'%s' queue" % queue.name,
            'failed': queue.name == 'failed',
        })
        return ctx
queue = QueueDetails.as_view()


class JobDetails(SuperUserMixin, generic.TemplateView):
    template_name = 'rq/job.html'

    def get_context_data(self, **kwargs):
        ctx = super(JobDetails, self).get_context_data(**kwargs)
        try:
            job = Job.fetch(self.kwargs['job'])
        except NoSuchJobError:
            raise Http404
        if job.exc_info:
            failed = True
            queue = get_failed_queue()
        else:
            failed = False
            queue = Queue(job.origin)
        ctx.update({
            'job': job,
            'queue': queue,
            'title': _('Job %s') % job.id,
            'failed': failed,
        })
        return ctx
job = JobDetails.as_view()


class WorkerDetails(SuperUserMixin, generic.TemplateView):
    template_name = 'rq/worker.html'

    def get_context_data(self, **kwargs):
        ctx = super(WorkerDetails, self).get_context_data(**kwargs)
        key = Worker.redis_worker_namespace_prefix + self.kwargs['worker']
        worker = Worker.find_by_key(key)
        ctx.update({
            'worker': worker,
            'title': _('Worker %s') % worker.name,
        })
        return ctx
worker = WorkerDetails.as_view()
