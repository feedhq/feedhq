import json

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.sites.requests import RequestSite
from django.core import signing
from django.core.mail import send_mail
from django.core.urlresolvers import reverse, reverse_lazy
from django.forms import Form
from django.shortcuts import redirect
from django.template import loader
from django.utils.translation import ugettext as _
from django.views import generic

from password_reset import views

from .forms import (ChangePasswordForm, CredentialsForm, DeleteAccountForm,
                    PocketForm, ProfileForm, ServiceForm, SharingForm,
                    WallabagForm)
from .. import es
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
        })
        entries = es.client.count(es.user_alias(self.request.user.pk),
                                  doc_type='entries')['count']
        ctx['entries'] = entries
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

    def get_initial(self):
        return {'ttl': self.request.user.ttl or 365}


profile = login_required(ProfileView.as_view())


class Sharing(UserMixin, generic.FormView):
    form_class = SharingForm
    template_name = 'profiles/sharing.html'
    success_url = reverse_lazy('sharing')


sharing = login_required(Sharing.as_view())


class Export(UserMixin, generic.TemplateView):
    template_name = 'profiles/export.html'


export = login_required(Export.as_view())


class ServiceView(generic.FormView):
    FORMS = {
        'readability': CredentialsForm,
        'readitlater': CredentialsForm,
        'instapaper': CredentialsForm,
        'pocket': PocketForm,
        'wallabag': WallabagForm,
        'none': ServiceForm,
    }
    success_url = reverse_lazy('read_later')

    def get_template_names(self):
        return ['profiles/services/%s.html' % self.kwargs['service']]

    def get_form_kwargs(self):
        kwargs = super(ServiceView, self).get_form_kwargs()
        kwargs.update({
            'request': self.request,
            'user': self.request.user,
            'service': self.kwargs['service'],
        })
        return kwargs

    def get_form_class(self):
        return self.FORMS[self.kwargs['service']]

    def form_valid(self, form):
        form.save()
        if hasattr(form, 'response'):
            return form.response
        if form.user.read_later:
            messages.success(
                self.request,
                _('You have successfully added %s as your reading list '
                  'service.') % form.user.get_read_later_display(),
            )
        else:
            messages.success(
                self.request,
                _('You have successfully disabled reading list integration.'),
            )
        return super(ServiceView, self).form_valid(form)


services = login_required(ServiceView.as_view())


class PocketReturn(generic.RedirectView):
    permanent = False

    def get_redirect_url(self):
        response = requests.post(
            'https://getpocket.com/v3/oauth/authorize',
            data=json.dumps({'consumer_key': settings.POCKET_CONSUMER_KEY,
                             'code': self.request.session['pocket_code']}),
            headers={'Content-Type': 'application/json',
                     'X-Accept': 'application/json'})
        self.request.user.read_later_credentials = json.dumps(response.json())
        self.request.user.read_later = self.request.user.POCKET
        self.request.user.save(update_fields=['read_later',
                                              'read_later_credentials'])
        del self.request.session['pocket_code']
        messages.success(
            self.request,
            _('You have successfully added Pocket as your reading list '
              'service.'))
        return reverse('read_later')


pocket = PocketReturn.as_view()


class Recover(views.Recover):
    search_fields = ['email']


recover = Recover.as_view()


class DestructionRequest(generic.FormView):
    form_class = Form
    template_name = 'profiles/user_request_delete.html'

    def form_valid(self, form):
        token = signing.dumps(self.request.user.pk, salt='delete_account')
        url = reverse('destroy_confirm', args=[token])
        context = {
            'user': self.request.user,
            'url': url,
            'site': RequestSite(self.request),
            'scheme': 'https' if self.request.is_secure() else 'http',
        }
        body = loader.render_to_string('email/account_delete.txt', context)
        subject = _('FeedHQ account deletion request')
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [self.request.user.email])
        return redirect('destroy_sent')


destroy = login_required(DestructionRequest.as_view())


class DestroyConfirm(generic.FormView):
    success_url = reverse_lazy('destroy_done')
    form_class = DeleteAccountForm
    template_name = 'profiles/user_confirm_delete.html'

    def dispatch(self, request, token):
        try:
            signing.loads(token, max_age=20*60, salt='delete_account')
            self.token = token
        except signing.BadSignature:
            return redirect(reverse('destroy_account'))
        return super(DestroyConfirm, self).dispatch(request, token)

    def get_form_kwargs(self):
        kwargs = super(DestroyConfirm, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        return redirect(self.get_success_url())


destroy_confirm = login_required(DestroyConfirm.as_view())


class DestroySent(generic.TemplateView):
    template_name = 'profiles/account_delete_sent.html'


destroy_sent = login_required(DestroySent.as_view())


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
