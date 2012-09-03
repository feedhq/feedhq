from django import forms
from rq import requeue_job


class QueueForm(forms.Form):
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

    def clean(self):
        actions = []
        for key in self.cleaned_data:
            if self.cleaned_data[key]:
                actions.append(key)
        if len(actions) != 1:
            raise forms.ValidationError('Only one action at a time')
        return actions[0]

    def save(self):
        action = self.cleaned_data
        if action == 'compact':
            self.queue.compact()
        elif action == 'empty':
            self.queue.empty()
        elif action == 'requeue':
            for job_id in self.queue.job_ids:
                requeue_job(job_id, connection=self.queue.connection)
