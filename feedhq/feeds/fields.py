from django import forms
from django.db import models
from django.utils.translation import ugettext_lazy as _


class URLField(models.TextField):
    description = _("URL")

    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.URLField,
            'widget': forms.TextInput,
        }
        defaults.update(kwargs)
        return super(URLField, self).formfield(**defaults)
