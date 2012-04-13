from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core import signing
from django.core.urlresolvers import reverse, reverse_lazy
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.translation import ugettext as _
from django.views import generic

from .forms import (ChangePasswordForm, ProfileForm, CredentialsForm,
                    ServiceForm, PasswordRecoveryForm, PasswordResetForm)
from ..decorators import login_required
from ..feeds.models import Feed


class ProfileView(generic.FormView):
    forms = {
        'password': ChangePasswordForm,
        'profile': ProfileForm,
    }
    template_name = 'auth/user_detail.html'

    def dispatch(self, request, *args, **kwargs):
        self.action = 'profile'
        if request.method == 'POST':
            self.action = request.POST.get('action', self.action)
        return super(ProfileView, self).dispatch(request, *args, **kwargs)

    def get_object(self):
        return self.request.user

    def get_form_class(self):
        return self.forms[self.action]

    def get_form_kwargs(self):
        kwargs = super(ProfileView, self).get_form_kwargs()
        kwargs.update({
            'instance': self.request.user,
        })
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super(ProfileView, self).get_context_data(**kwargs)
        ctx['%s_form' % self.action] = ctx['form']
        if self.action == 'password':
            ctx['profile_form'] = ProfileForm(**self.get_form_kwargs())
        else:
            ctx['password_form'] = ChangePasswordForm(**self.get_form_kwargs())
        del ctx['form']
        ctx.update({
            'categories': self.request.user.categories.count(),
            'feeds': Feed.objects.filter(
                category__user=self.request.user,
            ).count(),
            'entries': self.request.user.entries.count(),
        })
        return ctx

    def form_valid(self, form):
        form.save()
        messages.success(self.request, form.success_message)
        return redirect(reverse('profile'))
profile = login_required(ProfileView.as_view())


@login_required
def export(request):
    """OPML export"""
    response = render(request, 'profiles/opml_export.opml',
                      {'categories': request.user.categories.all()})
    response['Content-Disposition'] = 'attachment; filename=feedhq-export.opml'
    ctype = 'text/xml; charset=%s' % settings.DEFAULT_CONTENT_TYPE
    response['Content-Type'] = ctype
    return response


class ServiceView(generic.FormView):
    FORMS = {
        'readability': CredentialsForm,
        'readitlater': CredentialsForm,
        'instapaper': CredentialsForm,
        'none': ServiceForm,
    }
    success_url = reverse_lazy('profile')

    def get_template_names(self):
        return ['profiles/services/%s.html' % self.kwargs['service']]

    def get_form_kwargs(self):
        kwargs = super(ServiceView, self).get_form_kwargs()
        kwargs.update({
            'user': self.request.user,
            'service': self.kwargs['service'],
        })
        return kwargs

    def get_form_class(self):
        return self.FORMS[self.kwargs['service']]

    def form_valid(self, form):
        form.save()
        if form.user.read_later:
            messages.success(
                self.request,
                _('You have successfully added %s as your reading list '
                  'service') % form.user.get_read_later_display(),
            )
        else:
            messages.success(
                self.request,
                _('You have successfully disabled reading list integration'),
            )
        return super(ServiceView, self).form_valid(form)
services = login_required(ServiceView.as_view())


class Recover(generic.FormView):
    form_class = PasswordRecoveryForm
    template_name = 'profiles/recovery_form.html'

    def form_valid(self, form):
        form.save()
        context = {'email': form.cleaned_data['email']}
        return self.render_to_response(self.get_context_data(**context))
recover = Recover.as_view()


class Reset(generic.FormView):
    form_class = PasswordResetForm
    template_name = 'profiles/password_reset_form.html'
    success_url = reverse_lazy('recover_done')

    def dispatch(self, request, *args, **kwargs):
        self.request = request
        self.args = args
        self.kwargs = kwargs
        two_days = 3600 * 48
        try:
            username = signing.loads(kwargs['key'], max_age=two_days,
                                     salt="recover")
        except signing.BadSignature:
            return self.invalid()

        self.user = get_object_or_404(User, username=username)
        return super(Reset, self).dispatch(request, *args, **kwargs)

    def invalid(self):
        return self.render_to_response(self.get_context_data(invalid=True))

    def get_context_data(self, **kwargs):
        ctx = super(Reset, self).get_context_data(**kwargs)
        if 'invalid' not in ctx:
            ctx.update({
                'email': self.user.email,
                'key': self.kwargs['key'],
            })
        return ctx

    def get_form_kwargs(self):
        kwargs = super(Reset, self).get_form_kwargs()
        kwargs.update({
            'user': self.user,
        })
        return kwargs

    def form_valid(self, form):
        form.save()
        return super(Reset, self).form_valid(form)
reset = Reset.as_view()


class RecoverDone(generic.TemplateView):
    template_name = 'profiles/password_recovery_done.html'
recover_done = RecoverDone.as_view()
