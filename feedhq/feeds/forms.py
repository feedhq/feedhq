import urlparse

from django.forms.formsets import formset_factory
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _
from lxml.etree import XMLSyntaxError

import floppyforms as forms
import opml

from .models import Category, Feed


class ColorWidget(forms.Select):
    template_name = 'forms/color_select.html'


class UserFormMixin(object):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(UserFormMixin, self).__init__(*args, **kwargs)


class CategoryForm(UserFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'color']
        widgets = {
            'color': ColorWidget,
        }

    def save(self, commit=True):
        category = super(CategoryForm, self).save(commit=False)

        slug = slugify(self.cleaned_data['name'])
        if not slug:
            slug = 'unknown'
        valid = False
        candidate = slug
        num = 1
        while not valid:
            if candidate in ('add', 'import'):  # gonna conflict
                candidate = '{0}-{1}'.format(slug, num)
            categories = self.user.categories.filter(slug=candidate)
            if self.instance is not None:
                categories = categories.exclude(pk=self.instance.pk)
            if categories.exists():
                candidate = '{0}-{1}'.format(slug, num)
                num += 1
            else:
                valid = True
        slug = candidate

        category.slug = slug
        category.user = self.user
        if commit:
            category.save()
        return category


class FeedForm(UserFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(FeedForm, self).__init__(*args, **kwargs)
        self.fields['category'].queryset = self.user.categories.all()

    class Meta:
        model = Feed
        fields = ('name', 'url', 'category')

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

        existing = Feed.objects.filter(category__user=self.user, url=url)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise forms.ValidationError(
                _("It seems you're already subscribed to this feed."))
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
    action = forms.ChoiceField(
        choices=(
            ('read', 'read'),
        ),
        widget=forms.HiddenInput,
        initial='read',
    )


class SubscriptionForm(forms.Form):
    subscribe = forms.BooleanField(label=_('Subscribe?'), required=False)
    name = forms.CharField(label=_('Name'))
    url = forms.URLField(label=_('URL'))
    category = forms.ChoiceField(label=_('Category'))

SubscriptionFormSet = formset_factory(SubscriptionForm, extra=0)
