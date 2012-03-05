import pytz

from django.contrib.auth.models import User as DjangoUser
from django.db import models
from django.utils.translation import ugettext_lazy as _

from ..models import contribute_to_model

TIMEZONES = (
    (tz, _(tz)) for tz in pytz.common_timezones
)

ENTRIES_PER_PAGE = (
    (25, 25),
    (50, 50),
    (100, 100),
)


class User(models.Model):
    username = models.CharField(max_length=75, unique=True)
    timezone = models.CharField(_('Time zone'), max_length=75,
                                choices=TIMEZONES, default='UTC')
    entries_per_page = models.IntegerField(_('Entries per page'), default=25,
                                           choices=ENTRIES_PER_PAGE)

    class Meta:
        abstract = True

contribute_to_model(User, DjangoUser)
