import pytz

from django.contrib.auth.models import (AbstractBaseUser, UserManager,
                                        PermissionsMixin)
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from ..utils import get_redis_connection

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

    FONT_DROID_SANS = 'droid-sans'
    FONT_DROID_SERIF = 'droid-serif'
    FONT_GENTIUM_BASIC = 'gentium-basic'
    FONT_MERRIWEATHER = 'merriweather'
    FONT_PALATINO = 'palatino'
    FONT_POLY = 'poly'
    FONT_PT_SERIF = 'pt-serif'
    FONT_ABEL = 'abel'
    FONT_HELVETICA = 'helvetica'
    FONT_MULI = 'muli'
    FONT_OPEN_SANS = 'open-sans'
    FONT_PT_SANS = 'pt-sans'
    FONT_UBUNTU_CONDENSED = 'ubuntu-condensed'
    FONT_SOURCE_SANS_PRO = 'source-sans-pro'

    FONTS = (
        (
            _('Serif'), (
                (FONT_DROID_SERIF, 'Droid Serif'),
                (FONT_GENTIUM_BASIC, 'Gentium Basic'),
                (FONT_MERRIWEATHER, 'Merriweather'),
                (FONT_PALATINO, _('Palatino (system font)')),
                (FONT_POLY, 'Poly'),
                (FONT_PT_SERIF, 'PT Serif'),
            )
        ), (
            _('Sans Serif'), (
                (FONT_ABEL, 'Abel'),
                (FONT_DROID_SANS, 'Droid Sans'),
                (FONT_HELVETICA, _('Helvetica (system font)')),
                (FONT_MULI, 'Muli'),
                (FONT_OPEN_SANS, 'Open Sans'),
                (FONT_PT_SANS, 'PT Sans'),
                (FONT_UBUNTU_CONDENSED, 'Ubuntu Condensed'),
                (FONT_SOURCE_SANS_PRO, 'Source Sans Pro'),
            )
        )
    )

    username = models.CharField(max_length=75, unique=True)
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    email = models.CharField(max_length=75)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    timezone = models.CharField(_('Time zone'), max_length=75,
                                choices=TIMEZONES, default='UTC')
    entries_per_page = models.IntegerField(_('Entries per page'), default=50,
                                           choices=ENTRIES_PER_PAGE)
    endless_pages = models.BooleanField(
        _('Endless pages'), default=True,
        help_text=_("Check this box if you'd like to use a 'load more' "
                    "button instead of the page links."))

    oldest_first = models.BooleanField(
        _('Oldest entries first'), default=False,
        help_text=_("Check this box if you'd like to have the oldest "
                    "entries appear first."))
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

    font = models.CharField(
        _('Text font'), max_length=75, choices=FONTS, default=FONT_PT_SERIF,
        help_text=_('Non-system fonts are served by Google Web Fonts.'),
    )

    ttl = models.PositiveIntegerField(
        _('Retention days'), null=True,
        help_text=_('Number of days after which entries are deleted. The more '
                    'history you keep, the less snappy FeedHQ becomes.'))

    objects = UserManager()

    class Meta:
        db_table = 'auth_user'

    def get_short_name(self):
        return self.username

    @property
    def last_update_key(self):
        return 'user:{0}:updates'.format(self.pk)

    def last_updates(self):
        redis = get_redis_connection()
        values = redis.zrange(self.last_update_key, 0, 10**11, withscores=True)
        updates = {}
        for url, timestamp in values:
            updates[url.decode('utf-8')] = int(timestamp)
        return updates

    def refresh_updates(self):
        redis = get_redis_connection()
        last_updates = self.last_updates()
        urls = self.feeds.values_list('pk', 'url')
        for pk, url in urls:
            if url in last_updates:
                continue
            value = self.entries.filter(feed_id=pk).aggregate(
                date=Max('date'))['date']
            value = float(value.strftime('%s')) if value else 0
            redis.zadd(self.last_update_key, url, value)
        return self.last_updates()
