from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.utils.translation import ugettext_lazy as _
from ratelimitbackend import admin

from .models import User


class ProfileUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = '__all__'


def pop(tpl, index):
    """removes element at `index` and returns a new tuple"""
    return tpl[:index] + tpl[index+1:]


class ProfileUserAdmin(UserAdmin):
    form = ProfileUserChangeForm
    fieldsets = pop(UserAdmin.fieldsets, 1) + (
        (_('FeedHQ'), {'fields': ('email', 'is_suspended', 'timezone',
                                  'entries_per_page',
                                  'read_later', 'read_later_credentials',
                                  'sharing_twitter', 'sharing_gplus',
                                  'sharing_email', 'ttl')}),
    )
    search_fields = ('username', 'email')
    list_display = ('username', 'email', 'is_staff', 'is_suspended')
    list_filter = UserAdmin.list_filter + ('is_suspended',)


admin.site.register(User, ProfileUserAdmin)
