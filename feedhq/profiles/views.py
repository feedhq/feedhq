from django.contrib import messages
from django.contrib.sites.models import RequestSite
from django.core.urlresolvers import reverse_lazy
from django.shortcuts import redirect, render
from django.utils.translation import ugettext as _
from django.views import generic

from password_reset import views

from .forms import (ChangePasswordForm, ProfileForm, CredentialsForm,
                    ServiceForm, DeleteAccountForm, SharingForm)
from ..decorators import login_required


class UserMixin(object):
    success_url = reverse_lazy('profile')

    def get_object(self):
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super(UserMixin, self).get_form_kwargs()
        kwargs.update({
            'instance': self.request.user,
        })
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, form.success_message)
        return super(UserMixin, self).form_valid(form)


class Stats(UserMixin, generic.DetailView):
    def get_context_data(self, **kwargs):
        ctx = super(Stats, self).get_context_data(**kwargs)
        ctx.update({
            'categories': self.request.user.categories.count(),
            'feeds': self.request.user.feeds.count(),
            'entries': self.request.user.entries.count(),
        })
        return ctx
stats = login_required(Stats.as_view())


class ReadLater(UserMixin, generic.TemplateView):
    template_name = 'profiles/read_later.html'
read_later = login_required(ReadLater.as_view())


class PasswordView(UserMixin, generic.FormView):
    template_name = 'profiles/change_password.html'
    form_class = ChangePasswordForm
password = login_required(PasswordView.as_view())


class ProfileView(UserMixin, generic.FormView):
    form_class = ProfileForm
    template_name = 'profiles/edit_profile.html'
profile = login_required(ProfileView.as_view())


class Sharing(UserMixin, generic.FormView):
    form_class = SharingForm
    template_name = 'profiles/sharing.html'
    success_url = reverse_lazy('sharing')
sharing = login_required(Sharing.as_view())


class Export(UserMixin, generic.TemplateView):
    template_name = 'profiles/export.html'
export = login_required(Export.as_view())


@login_required
def opml_export(request):
    """OPML export"""
    response = render(request, 'profiles/opml_export.opml',
                      {'categories': request.user.categories.all()})
    response['Content-Disposition'] = 'attachment; filename=feedhq-export.opml'
    response['Content-Type'] = 'text/xml; charset=utf-8'
    return response


class ServiceView(generic.FormView):
    FORMS = {
        'readability': CredentialsForm,
        'readitlater': CredentialsForm,
        'instapaper': CredentialsForm,
        'none': ServiceForm,
    }
    success_url = reverse_lazy('read_later')

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


class Recover(views.Recover):
    search_fields = ['email']
recover = Recover.as_view()


class Destroy(generic.FormView):
    success_url = reverse_lazy('destroy_done')
    form_class = DeleteAccountForm
    template_name = 'profiles/user_confirm_delete.html'

    def get_form_kwargs(self):
        kwargs = super(Destroy, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        return redirect(self.get_success_url())
destroy = login_required(Destroy.as_view())


class DestroyDone(generic.TemplateView):
    template_name = 'profiles/account_delete_done.html'
destroy_done = DestroyDone.as_view()


class Bookmarklet(generic.TemplateView):
    template_name = 'profiles/bookmarklet.html'

    def get_context_data(self, **kwargs):
        ctx = super(Bookmarklet, self).get_context_data(**kwargs)
        ctx['site'] = RequestSite(self.request)
        ctx['scheme'] = 'https' if self.request.is_secure() else 'http'
        return ctx
bookmarklet = login_required(Bookmarklet.as_view())
