from django import forms
from rq import requeue_job, cancel_job


class ActionForm(forms.Form):
    def clean(self):
        actions = [key for key in self.cleaned_data if self.cleaned_data[key]]
        if len(actions) != 1:
            raise forms.ValidationError('Only one action at a time')
        return actions[0]


class QueueForm(ActionForm):
    requeue = forms.CharField(required=False)
    compact = forms.CharField(required=False)
    empty = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        self.queue = kwargs.pop('queue')
        super(QueueForm, self).__init__(*args, **kwargs)

    def clean_requeue(self):
        return bool(self.cleaned_data['requeue'])

    def clean_compact(self):
        return bool(self.cleaned_data['compact'])

    def clean_empty(self):
        return bool(self.cleaned_data['empty'])

    def save(self):
        action = self.cleaned_data
        if action == 'compact':
            self.queue.compact()
        elif action == 'empty':
            self.queue.empty()
        elif action == 'requeue':
            for job_id in self.queue.job_ids:
                requeue_job(job_id, connection=self.queue.connection)


class JobForm(ActionForm):
    requeue = forms.CharField(required=False)
    cancel = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        self.job = kwargs.pop('job')
        super(JobForm, self).__init__(*args, **kwargs)

    def clean_requeue(self):
        return bool(self.cleaned_data['requeue'])

    def clean_cancel(self):
        return bool(self.cleaned_data['cancel'])

    def save(self):
        action = self.cleaned_data
        print self.job.id
        if action == 'requeue':
            requeue_job(self.job.id, connection=self.job.connection)
        elif action == 'cancel':
            cancel_job(self.job.id, connection=self.job.connection)
