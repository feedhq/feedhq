import pytz

from django.contrib.auth.models import User as DjangoUser
from django.db import models
from django.utils.translation import ugettext_lazy as _

from ..models import contribute_to_model

TIMEZONES = (
    (tz, _(tz)) for tz in pytz.all_timezones
)


class User(models.Model):
    username = models.CharField(max_length=75, unique=True)
    timezone = models.CharField(_('Time zone'), max_length=75,
                                choices=TIMEZONES, default='UTC')

    class Meta:
        abstract = True

contribute_to_model(User, DjangoUser)
