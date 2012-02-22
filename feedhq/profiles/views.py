from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.utils.translation import ugettext as _
from django.views import generic

from .forms import ChangePasswordForm
from ..decorators import login_required
from ..feeds.models import Feed


class ProfileView(generic.FormView):
    form_class = ChangePasswordForm
    template_name = 'auth/user_detail.html'

    def get_object(self):
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super(ProfileView, self).get_form_kwargs()
        kwargs.update({
            'user': self.request.user,
        })
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super(ProfileView, self).get_context_data(**kwargs)
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
        messages.success(self.request,
                         _('Your password was changed successfully'))
        return redirect(reverse('profile'))
profile = login_required(ProfileView.as_view())
