import urlparse

from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _

import floppyforms as forms

from .models import Category, Feed


class ColorWidget(forms.Select):
    template_name = 'forms/color_select.html'


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        exclude = ('user', 'slug', 'order')
        widgets = {
            'color': ColorWidget,
        }

    def clean_name(self):
        """Generates a slug and ensures it is unique for this user"""
        self.slug = slugify(self.cleaned_data['name'])
        valid = False
        while not valid:
            if self.slug in ('add', 'import'):  # gonna conflict
                self.slug = '%s-' % self.slug
            try:  # Maybe a category with this slug already exists...
                Category.objects.get(user=self.user, slug=self.slug)
                self.slug = self.slug + '-'
            except Category.DoesNotExist:  # ... or not
                valid = True
        return self.cleaned_data['name']


class FeedForm(forms.ModelForm):
    class Meta:
        model = Feed
        fields = ('name', 'url', 'category', 'muted')

    def clean_url(self):
        url = self.cleaned_data['url']
        parsed = urlparse.urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            raise forms.ValidationError(
                _("Invalid URL scheme: '%s'. Only HTTP and HTTPS are "
                  "supported.") % parsed.scheme)

        netloc = parsed.netloc.split(':')[0]
        if netloc in ['localhost', '127.0.0.1', '::1']:
            raise forms.ValidationError(_("Invalid URL."))
        return url


class OPMLImportForm(forms.Form):
    file = forms.FileField()


class ActionForm(forms.Form):
    action = forms.ChoiceField(choices=(
        ('images', 'images'),
        ('unread', 'unread'),
        ('read_later', 'read_later'),
    ))


class ReadForm(forms.Form):
    action = forms.ChoiceField(choices=(
        ('read', 'read'),
    ), widget=forms.HiddenInput, initial='read')


class SubscriptionForm(forms.Form):
    subscribe = forms.BooleanField(label=_('Subscribe?'), required=False)
    name = forms.CharField(label=_('Name'))
    url = forms.URLField(label=_('URL'))
    category = forms.ChoiceField(label=_('Category'))
