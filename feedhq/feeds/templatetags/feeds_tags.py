from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def smart_date(value):
    now = timezone.localtime(timezone.now(), value.tzinfo)
    if value.year == now.year:
        if value.month == now.month and value.day == now.day:
            return value.strftime('%H:%M')
        return value.strftime('%b %d')
    return value.strftime('%b %d, %Y')


@register.filter
def smart_datetime(value):
    now = timezone.localtime(timezone.now(), value.tzinfo)
    if value.year == now.year:
        return value.strftime('%b %d, %H:%M')
    return value.strftime('%b %d, %Y')
