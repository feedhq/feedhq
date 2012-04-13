import json
import oauth2 as oauth
import requests
import urllib
import urlparse

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import signing
from django.core.mail import send_mail
from django.template import loader
from django.utils.translation import ugettext_lazy as _

import floppyforms as forms


class ProfileForm(forms.ModelForm):
    success_message = _('Your profile was updated successfully')
    action = forms.CharField(widget=forms.HiddenInput, initial='profile')

    class Meta:
        model = User
        fields = ['timezone', 'entries_per_page']


class ChangePasswordForm(forms.Form):
    success_message = _('Your password was changed successfully')

    action = forms.CharField(widget=forms.HiddenInput, initial='password')
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
        super(ServiceForm, self).__init__(*args, **kwargs)

    def clean(self):
        getattr(self, 'check_%s' % self.service)()
        return self.cleaned_data

    def save(self):
        self.user.read_later = '' if self.service == 'none' else self.service
        self.user.save()

    def check_none(self):
        self.user.read_later_credentials = ''


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
        consumer = oauth.Consumer(key, secret)
        client = oauth.Client(consumer)
        client.set_signature_method(oauth.SignatureMethod_HMAC_SHA1())
        params = {
            'x_auth_username': self.cleaned_data['username'],
            'x_auth_password': self.cleaned_data['password'],
            'x_auth_mode': 'client_auth',
        }
        response, token = client.request(token_url, method='POST',
                                         body=urllib.urlencode(params))
        if response.status != 200:
            raise forms.ValidationError(
                _("Unable to verify your %s credentials. Please double-check "
                  "and try again") % self.service,
            )
        request_token = dict(urlparse.parse_qsl(token))
        self.user.read_later_credentials = json.dumps(request_token)


def send_recovery_email(user):
    value = signing.dumps(user.username, salt='recover')
    site = Site.objects.get_current()
    context = {
        'site': site,
        'user': user,
        'value': value,
    }
    body = loader.render_to_string('profiles/recover_email.txt', context)
    send_mail(_('Password recovery on %s') % site.domain, body,
              settings.DEFAULT_FROM_EMAIL, [user.email])


class PasswordRecoveryForm(forms.Form):
    email = forms.CharField()

    def clean_email(self):
        email = self.cleaned_data['email']
        try:
            self.user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise forms.ValidationError(
                _("This account doesn't exist. Make sure the email is "
                  "spelled correctly, note that it's case-sensitive."),
            )
        return email

    def save(self):
        send_recovery_email(self.user)


class PasswordResetForm(forms.Form):
    password1 = forms.CharField(label=_('New password'),
                               widget=forms.PasswordInput)
    password2 = forms.CharField(label=_('New password (confirm)'),
                                widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super(PasswordResetForm, self).__init__(*args, **kwargs)

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1', '')
        password2 = self.cleaned_data['password2']
        if password1 != password2:
            raise forms.ValidationError(_("Please enter the same password "
                                          "twice. The two passwords didn't "
                                          "match."))
        return password2

    def save(self):
        self.user.set_password(self.cleaned_data['password2'])
        self.user.save()
