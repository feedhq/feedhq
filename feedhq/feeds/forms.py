import contextlib
import urlparse

from django.core.cache import cache
from django.forms.formsets import formset_factory
from django.utils.translation import ugettext_lazy as _
from lxml.etree import XMLSyntaxError

import feedparser
import floppyforms as forms
import opml
import requests

from .models import Category, Feed
from .utils import USER_AGENT


@contextlib.contextmanager
def user_lock(cache_key, user_id):
    key = "lock:{0}:{1}".format(cache_key, user_id)

    redis = cache._client
    got_lock = redis.setnx(key, user_id)
    if not got_lock:
        raise forms.ValidationError(
            _("This action can only be done one at a time."))
    try:
        yield
    finally:
        if got_lock:
            redis.delete(key)


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

    def clean_name(self):
        name = self.cleaned_data['name']
        existing = self.user.categories.filter(name=name)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                _("A category with this name already exists."))
        return name

    def save(self, commit=True):
        category = super(CategoryForm, self).save(commit=False)
        category.user = self.user
        if commit:
            category.save(update_slug=True)
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

        existing = self.user.feeds.filter(url=url)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise forms.ValidationError(
                _("It seems you're already subscribed to this feed."))

        # Check this is actually a feed
        with user_lock("feed_check", self.user.pk):
            headers = {
                'User-Agent': USER_AGENT % 'checking feed',
                'Accept': feedparser.ACCEPT_HEADER,
            }
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                raise forms.ValidationError(_(
                    "Invalid response code from URL: "
                    "HTTP %s.") % response.status_code)
        parsed = feedparser.parse(response.content)
        if parsed.bozo or not hasattr(parsed.feed, 'title'):
            raise forms.ValidationError(
                _("This URL doesn't seem to be a valid feed."))
        return url

    def save(self, commit=True):
        feed = super(FeedForm, self).save(commit=False)
        feed.user = self.user
        if commit:
            feed.save()
        return feed


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
    name = forms.CharField(label=_('Name'), required=False)
    url = forms.URLField(label=_('URL'))
    category = forms.ChoiceField(label=_('Category'), required=False)

    def clean_url(self):
        url = self.cleaned_data['url']
        if (
            self.cleaned_data.get('subscribe', False) and
            self.user.feeds.filter(url=url).exists()
        ):
            raise forms.ValidationError(
                _("You are already subscribed to this feed."))
        return url

    def clean_name(self):
        if (
            self.cleaned_data.get('subscribe', False) and
            not self.cleaned_data['name']
        ):
            raise forms.ValidationError(_('This field is required.'))
        return self.cleaned_data['name']

SubscriptionFormSet = formset_factory(SubscriptionForm, extra=0)
