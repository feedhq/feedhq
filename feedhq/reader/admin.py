from ratelimitbackend import admin

from .models import AuthToken


class AuthTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'date_created', 'preview', 'user_pk',
                    'cache_value')
    raw_id_fields = ('user',)

admin.site.register(AuthToken, AuthTokenAdmin)
