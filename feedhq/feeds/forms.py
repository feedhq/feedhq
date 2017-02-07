import contextlib
import json
import os

import feedparser
import floppyforms.__future__ as forms
import opml
import requests
import six

from django.core.cache import cache
from django.core.validators import URLValidator, validate_ipv46_address
from django.db import transaction
from django.forms.formsets import formset_factory
from django.utils.translation import ugettext_lazy as _
from lxml.etree import XMLSyntaxError
from raven import Client
from urlobject import URLObject

from .models import Category, Feed
from .utils import is_feed, USER_AGENT
from .. import es
from ..utils import get_redis_connection


@contextlib.contextmanager
def user_lock(cache_key, user_id, timeout=None):
    key = "lock:{0}:{1}".format(cache_key, user_id)

    redis = get_redis_connection()
    got_lock = redis.setnx(key, user_id)
    if timeout is not None and got_lock:
        redis.setex(key, timeout, user_id)
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
        if len(name) > 50:
            raise forms.ValidationError(
                _("This name is too long. Please shorten it to 50 "
                  "characters or less."))
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
        self.fields['url'].validators = []

    class Meta:
        model = Feed
        fields = ('name', 'url', 'category')

    def clean_url(self):
        url = URLObject(self.cleaned_data['url'])

        # URLObject doesn't handle ipv6 very well yet. In the meantime, ...
        if url.netloc.count(':') > 3:
            raise forms.ValidationError(_("Enter a valid URL."))

        URLValidator()(url.without_auth())
        if url.scheme not in ['http', 'https']:
            raise forms.ValidationError(
                _("Invalid URL scheme: '%s'. Only HTTP and HTTPS are "
                  "supported.") % url.scheme)

        if url.netloc.hostname in ['localhost', '127.0.0.1', '::1']:
            raise forms.ValidationError(_("Enter a valid URL."))

        try:
            validate_ipv46_address(url.netloc.hostname)
        except forms.ValidationError:
            pass
        else:
            raise forms.ValidationError(_("Enter a valid URL."))

        existing = self.user.feeds.filter(url=url)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise forms.ValidationError(
                _("It seems you're already subscribed to this feed."))

        auth = None
        if url.auth != (None, None):
            auth = url.auth

        # Check this is actually a feed
        with user_lock("feed_check", self.user.pk, timeout=30):
            headers = {
                'User-Agent': USER_AGENT % 'checking feed',
                'Accept': feedparser.ACCEPT_HEADER,
            }
            try:
                response = requests.get(six.text_type(url.without_auth()),
                                        headers=headers, timeout=10,
                                        auth=auth)
            except Exception:
                if 'SENTRY_DSN' in os.environ:
                    client = Client()
                    client.captureException()
                raise forms.ValidationError(_("Error fetching the feed."))
            if response.status_code != 200:
                raise forms.ValidationError(_(
                    "Invalid response code from URL: "
                    "HTTP %s.") % response.status_code)
        try:
            parsed = feedparser.parse(response.content)
        except Exception:
            raise forms.ValidationError(_("Error parsing the feed."))
        if not is_feed(parsed):
            raise forms.ValidationError(
                _("This URL doesn't seem to be a valid feed."))
        self.cleaned_data['title'] = parsed.feed.title
        # Cache this in case update_favicon needs it and it's not in the
        # scheduler data yet.
        if hasattr(parsed.feed, 'link'):
            cache.set(u'feed_link:{0}'.format(url), parsed.feed.link, 600)
        return url

    @transaction.atomic
    def save(self):
        feed = super(FeedForm, self).save(commit=False)
        feed.user = self.user

        if (
            feed.tracker.has_changed('category_id') and
            feed.tracker.previous('id')
        ):
            new_cat = feed.category_id
            entries = es.manager.user(self.user).filter(
                feed=feed.pk).aggregate('id').fetch(per_page=0)
            pks = [bucket['key'] for bucket in entries[
                'aggregations']['entries']['query']['id']['buckets']]
            if pks:
                ops = [{
                    '_op_type': 'update',
                    '_type': 'entries',
                    '_id': pk,
                    'doc': {'category': new_cat},
                } for pk in pks]
                index = es.user_alias(self.user.pk)
                es.bulk(ops, index=index, raise_on_error=True)
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
        ('star', 'star'),
        ('unstar', 'unstar'),
    ))


class ReadForm(forms.Form):
    READ_ALL = 'read-all'
    READ_PAGE = 'read-page'

    action = forms.ChoiceField(
        choices=(
            (READ_ALL, 'read all'),
            (READ_PAGE, 'read page'),
        ),
        widget=forms.HiddenInput,
        initial='read-all',
    )

    def __init__(self, es_entries=None, feed=None, category=None,
                 user=None, pages_only=False, *args, **kwargs):
        self.es_entries = es_entries
        self.feed = feed
        self.category = category
        self.user = user
        self.pages_only = pages_only
        super(ReadForm, self).__init__(*args, **kwargs)
        if self.pages_only:
            self.fields['entries'] = forms.CharField(widget=forms.HiddenInput)

    def clean_entries(self):
        return json.loads(self.cleaned_data['entries'])

    def save(self):
        index = es.user_alias(self.user.pk)
        if self.pages_only:
            pks = self.cleaned_data['entries']
        else:
            # Fetch all IDs for current query.
            entries = self.es_entries.filter(
                read=False).aggregate('id').fetch(per_page=0)
            pks = [bucket['key'] for bucket in entries[
                'aggregations']['entries']['query']['id']['buckets']]

        ops = [{
            '_op_type': 'update',
            '_index': index,
            '_type': 'entries',
            '_id': pk,
            'doc': {'read': True},
        } for pk in pks]
        if pks:
            with es.ignore_bulk_error(404, 409):
                es.bulk(ops, raise_on_error=True, params={'refresh': True})
        return pks


class UndoReadForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ('undo-read', 'undo-read'),
        ),
        widget=forms.HiddenInput,
        initial='undo-read',
    )
    pks = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, user=None, *args, **kwargs):
        self.user = user
        super(UndoReadForm, self).__init__(*args, **kwargs)

    def clean_pks(self):
        return json.loads(self.cleaned_data['pks'])

    def save(self):
        pks = self.cleaned_data['pks']
        index = es.user_alias(self.user.pk)
        ops = [{
            '_op_type': 'update',
            '_index': index,
            '_type': 'entries',
            '_id': pk,
            'doc': {'read': False},
        } for pk in pks]
        with es.ignore_bulk_error(404, 409):
            es.bulk(ops, raise_on_error=True, params={'refresh': True})
        return len(pks)


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
