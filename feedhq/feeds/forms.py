import urlparse

from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _
from lxml.etree import XMLSyntaxError

import floppyforms as forms
import opml

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
        if not self.slug:
            self.slug = 'unknown'
        valid = False
        candidate = self.slug
        num = 1
        while not valid:
            if candidate in ('add', 'import'):  # gonna conflict
                candidate = '{0}-{1}'.format(self.slug, num)
            try:  # Maybe a category with this slug already exists...
                Category.objects.get(user=self.user, slug=candidate)
                candidate = '{0}-{1}'.format(self.slug, num)
                num += 1
            except Category.DoesNotExist:  # ... or not
                valid = True
        self.slug = candidate
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


class OPMLField(forms.FileField):
    def to_python(self, data):
        f = super(OPMLField, self).to_python(data)
        if f is None:
            return

        if hasattr(data, 'read'):
            content = data.read()
        else:
            content = data['content']
        try:
            opml.from_string(content)
        except XMLSyntaxError:
            raise forms.ValidationError(
                _("This file doesn't seem to be a valid OPML file."))

        if hasattr(f, 'seek') and callable(f.seek):
            f.seek(0)
        return f


class OPMLImportForm(forms.Form):
    file = OPMLField()


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
