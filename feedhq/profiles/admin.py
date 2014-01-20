from ratelimitbackend import admin

from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.utils.translation import ugettext_lazy as _

from .models import User


class ProfileUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = '__all__'


class ProfileUserAdmin(UserAdmin):
    form = ProfileUserChangeForm
    fieldsets = UserAdmin.fieldsets + (
        (_('FeedHQ'), {'fields': ('is_suspended', 'timezone',
                                  'entries_per_page',
                                  'read_later', 'read_later_credentials',
                                  'sharing_twitter', 'sharing_gplus',
                                  'sharing_email', 'ttl')}),
    )
    list_display = ('username', 'email', 'is_staff', 'is_suspended')
    list_filter = UserAdmin.list_filter + ('is_suspended',)


admin.site.register(User, ProfileUserAdmin)
