VERSION = (0, 1)


def get_version():
    return ".".join(map(str, VERSION))

__version__ = get_version()

try:
    # don't break setup.py if django hasn't been installed yet
    from django.template.loader import add_to_builtins
    add_to_builtins('django.templatetags.i18n')
    add_to_builtins('django.templatetags.future')
    add_to_builtins('django.templatetags.tz')
except ImportError:
    pass
