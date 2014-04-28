import json
import requests

from requests_oauthlib import OAuth1
from six.moves.urllib import parse as urlparse

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db import transaction
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _

import floppyforms as forms

from ratelimitbackend.forms import AuthenticationForm

from .. import es
from .models import User


class AuthForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super(AuthForm, self).__init__(*args, **kwargs)
        self.fields['username'].label = _('Username or Email')


class ProfileForm(forms.ModelForm):
    success_message = _('Your profile was updated successfully')

    class Meta:
        model = User
        fields = ['username', 'timezone', 'entries_per_page', 'font',
                  'endless_pages', 'oldest_first', 'allow_media', 'ttl']

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.exclude(pk=self.instance.pk).filter(
            username__iexact=username,
        ).exists():
            raise forms.ValidationError(_('This username is already taken.'))
        return username

    def clean_ttl(self):
        try:
            ttl = int(self.cleaned_data['ttl'])
        except ValueError:
            raise forms.ValidationError(_('Please enter an integer value.'))
        if ttl > 365 or ttl < 2:
            raise forms.ValidationError(
                _('Please enter a value between 2 and 365.'))
        return ttl


class SharingForm(forms.ModelForm):
    success_message = _('Your sharing preferences were updated successfully')

    class Meta:
        model = User
        fields = ['sharing_twitter', 'sharing_gplus', 'sharing_email']


class ChangePasswordForm(forms.Form):
    success_message = _('Your password was changed successfully')
    current_password = forms.CharField(label=_('Current password'),
                                       widget=forms.PasswordInput)
    new_password = forms.CharField(label=_('New password'),
                                   widget=forms.PasswordInput)
    new_password2 = forms.CharField(label=_('New password (confirm)'),
                                    widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('instance')
        super(ChangePasswordForm, self).__init__(*args, **kwargs)

    def clean_current_password(self):
        password = self.cleaned_data['current_password']
        if not self.user.check_password(password):
            raise forms.ValidationError(_('Incorrect password'))
        return password

    def clean_new_password2(self):
        password_1 = self.cleaned_data.get('new_password', '')
        if self.cleaned_data['new_password2'] != password_1:
            raise forms.ValidationError(_("The two passwords didn't match"))
        return password_1

    def save(self):
        self.user.set_password(self.cleaned_data['new_password'])
        self.user.save()


class ServiceForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.service = kwargs.pop('service')
        self.request = kwargs.pop('request')
        super(ServiceForm, self).__init__(*args, **kwargs)

    def clean(self):
        getattr(self, 'check_%s' % self.service)()
        return self.cleaned_data

    def save(self):
        self.user.read_later = '' if self.service == 'none' else self.service
        self.user.save()

    def check_none(self):
        self.user.read_later_credentials = ''


class PocketForm(ServiceForm):
    def check_pocket(self):
        url = 'https://getpocket.com/v3/oauth/request'
        redirect_uri = self.request.build_absolute_uri(
            reverse('pocket_return'))
        data = {
            'consumer_key': settings.POCKET_CONSUMER_KEY,
            'redirect_uri': redirect_uri,
        }
        response = requests.post(url, data=json.dumps(data),
                                 headers={'Content-Type': 'application/json',
                                          'X-Accept': 'application/json'})
        code = response.json()['code']
        self.request.session['pocket_code'] = code
        self.response = redirect(
            'https://getpocket.com/auth/authorize?{0}'.format(
                urlparse.urlencode({'request_token': code,
                                    'redirect_uri': redirect_uri})))


class WallabagForm(ServiceForm):
    url = forms.URLField(
        label=_('Wallabag URL'),
        help_text=_('Your Wallabag URL, e.g. '
                    'https://www.framabag.org/u/username'))

    def check_wallabag(self):
        self.user.read_later_credentials = json.dumps({
            'wallabag_url': self.cleaned_data['url'],
        })


class CredentialsForm(ServiceForm):
    """A form that checks an external service using Basic Auth on a URL"""
    username = forms.CharField(label=_('Username'))
    password = forms.CharField(label=_('Password'), widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super(CredentialsForm, self).__init__(*args, **kwargs)
        if self.service == 'instapaper':
            self.fields['username'].help_text = _('Your Instapaper username '
                                                  'is an email address.')

    def check_readitlater(self):
        """Checks that the readitlater credentials are valid"""
        data = self.cleaned_data
        data['apikey'] = settings.API_KEYS['readitlater']
        response = requests.get('https://readitlaterlist.com/v2/auth',
                                params=data)
        if response.status_code != 200:
            raise forms.ValidationError(
                _('Unable to verify your readitlaterlist credentials. Please '
                  'double-check and try again.')
            )
        self.user.read_later_credentials = json.dumps(self.cleaned_data)

    def check_instapaper(self):
        """Get an OAuth token using xAuth from Instapaper"""
        self.check_xauth(
            settings.INSTAPAPER['CONSUMER_KEY'],
            settings.INSTAPAPER['CONSUMER_SECRET'],
            'https://www.instapaper.com/api/1/oauth/access_token',
        )

    def check_readability(self):
        """Get an OAuth token using the Readability API"""
        self.check_xauth(
            settings.READABILITY['CONSUMER_KEY'],
            settings.READABILITY['CONSUMER_SECRET'],
            'https://www.readability.com/api/rest/v1/oauth/access_token/',
        )

    def check_xauth(self, key, secret, token_url):
        """Check a generic xAuth provider"""
        auth = OAuth1(key, secret)
        params = {
            'x_auth_username': self.cleaned_data['username'],
            'x_auth_password': self.cleaned_data['password'],
            'x_auth_mode': 'client_auth',
        }
        response = requests.post(token_url, auth=auth, data=params)
        if response.status_code != 200:
            raise forms.ValidationError(
                _("Unable to verify your %s credentials. Please double-check "
                  "and try again") % self.service,
            )
        request_token = dict(urlparse.parse_qsl(response.text))
        self.user.read_later_credentials = json.dumps(request_token)


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput,
        label=_('Password'),
        help_text=_('Please enter your password to confirm your ownership '
                    'of this account.')
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(DeleteAccountForm, self).__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data['password']
        correct = self.user.check_password(password)
        if not correct:
            raise forms.ValidationError(_('The password you entered was '
                                          'incorrect.'))
        return password

    @transaction.atomic
    def save(self):
        user_id = self.user.pk
        self.user.delete()
        if self.user.es:
            es.client.delete_by_query(
                index=es.user_alias(user_id),
                doc_type='entries',
                body={'query': {'filtered': {'filter': {'match_all': {}}}}},
            )
