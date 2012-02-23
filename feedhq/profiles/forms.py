from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _

import floppyforms as forms


class ProfileForm(forms.ModelForm):
    success_message = _('Your profile was updated successfully')
    action = forms.CharField(widget=forms.HiddenInput, initial='profile')

    class Meta:
        model = User
        fields = ['timezone']


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
