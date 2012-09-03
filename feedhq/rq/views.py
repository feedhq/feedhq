import redis

from django.contrib import messages
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import Http404
from django.utils.translation import ugettext_lazy as _, ugettext as __
from django.views import generic

from rq import Queue, Worker, get_failed_queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from .forms import QueueForm


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

        opts = getattr(settings, 'RQ', {}).copy()
        opts.pop('eager', None)
        self.connection = redis.Redis(**opts)

        return super(SuperUserMixin, self).dispatch(request, *args, **kwargs)


class Stats(SuperUserMixin, generic.TemplateView):
    template_name = 'rq/stats.html'

    def get_context_data(self, **kwargs):
        ctx = super(Stats, self).get_context_data(**kwargs)
        ctx.update({
            'queues': Queue.all(connection=self.connection),
            'workers': Worker.all(connection=self.connection),
            'title': 'RQ Status',
        })
        return ctx
stats = Stats.as_view()


class QueueDetails(SuperUserMixin, generic.FormView):
    template_name = 'rq/queue.html'
    form_class = QueueForm

    def get_success_url(self):
        return reverse('rq_queue', kwargs=self.kwargs)

    def get_context_data(self, **kwargs):
        ctx = super(QueueDetails, self).get_context_data(**kwargs)
        queue = Queue(self.kwargs['queue'], connection=self.connection)
        ctx.update({
            'queue': queue,
            'jobs': [serialize_job(job) for job in queue.jobs],
            'title': "'%s' queue" % queue.name,
            'failed': queue.name == 'failed',
        })
        return ctx

    def get_form_kwargs(self):
        kwargs = super(QueueDetails, self).get_form_kwargs()
        kwargs['queue'] = Queue(self.kwargs['queue'],
                                connection=self.connection)
        return kwargs

    def form_valid(self, form):
        form.save()
        msgs = {
            'compact': __('Queue compacted'),
            'empty': __('Queue emptied'),
            'requeue': __('Jobs requeued'),
        }
        messages.success(self.request, msgs[form.cleaned_data])
        return super(QueueDetails, self).form_valid(form)
queue = QueueDetails.as_view()


class JobDetails(SuperUserMixin, generic.TemplateView):
    template_name = 'rq/job.html'

    def get_context_data(self, **kwargs):
        ctx = super(JobDetails, self).get_context_data(**kwargs)
        try:
            job = Job.fetch(self.kwargs['job'], connection=self.connection)
        except NoSuchJobError:
            raise Http404
        if job.exc_info:
            failed = True
            queue = get_failed_queue(connection=self.connection)
        else:
            failed = False
            queue = Queue(job.origin, connection=self.connection)
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
        worker = Worker.find_by_key(key, connection=self.connection)
        ctx.update({
            'worker': worker,
            'title': _('Worker %s') % worker.name,
        })
        return ctx
worker = WorkerDetails.as_view()
