from django.apps import AppConfig
from django.template.base import add_to_builtins


class FeedhqConfig(AppConfig):
    name = 'feedhq.core'

    def ready(self):
        add_to_builtins('django.templatetags.i18n')
        add_to_builtins('django.templatetags.tz')
