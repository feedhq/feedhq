import pytz

from django.contrib.auth.models import User as DjangoUser
from django.db import models
from django.utils.translation import ugettext_lazy as _

from ..models import contribute_to_model

TIMEZONES = [
    (tz, _(tz)) for tz in pytz.common_timezones
]

ENTRIES_PER_PAGE = (
    (25, 25),
    (50, 50),
    (100, 100),
)


class User(models.Model):
    NONE = ''
    READABILITY = 'readability'
    READITLATER = 'readitlater'
    INSTAPAPER = 'instapaper'
    READ_LATER_SERVICES = (
        (NONE, _('None')),
        (READABILITY, u'Readability'),
        (READITLATER, u'Read it later'),
        (INSTAPAPER, u'Instapaper'),
    )

    username = models.CharField(max_length=75, unique=True)
    timezone = models.CharField(_('Time zone'), max_length=75,
                                choices=TIMEZONES, default='UTC')
    entries_per_page = models.IntegerField(_('Entries per page'), default=50,
                                           choices=ENTRIES_PER_PAGE)
    read_later = models.CharField(_('Read later service'), blank=True,
                                  choices=READ_LATER_SERVICES, max_length=50)
    read_later_credentials = models.TextField(_('Read later credentials'),
                                              blank=True)

    sharing_twitter = models.BooleanField(_('Enable tweet button'),
                                          default=False)
    sharing_gplus = models.BooleanField(_('Enable +1 button (Google+)'),
                                        default=False)
    sharing_email = models.BooleanField(_('Enable Mail button'), default=False)

    class Meta:
        abstract = True

contribute_to_model(User, DjangoUser)
