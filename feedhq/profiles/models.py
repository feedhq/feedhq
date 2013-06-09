import pytz

from django.contrib.auth.models import (AbstractBaseUser, UserManager,
                                        PermissionsMixin)
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

TIMEZONES = [
    (tz, _(tz)) for tz in pytz.common_timezones
]

ENTRIES_PER_PAGE = (
    (25, 25),
    (50, 50),
    (100, 100),
)


class User(PermissionsMixin, AbstractBaseUser):
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

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
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    email = models.CharField(max_length=75)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
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

    allow_media = models.BooleanField(_('Automatically allow external media'),
                                      default=False)

    objects = UserManager()

    class Meta:
        db_table = 'auth_user'

    def get_short_name(self):
        return self.username
