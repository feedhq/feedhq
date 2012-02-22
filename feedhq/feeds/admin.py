from ratelimitbackend import admin

from django.contrib.auth.models import User, Group
from django.contrib.sites.models import Site
from django_push.subscriber.models import Subscription

from .models import Category, Feed, Entry


class FeedInline(admin.TabularInline):
    model = Feed


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'user')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
            (None, {
                'fields': (('name', 'slug'), 'user', 'order'),
            }),
    )
    inlines = [FeedInline]


class FeedAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'unread_count', 'favicon_img')


class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'user')


admin.site.register(Category, CategoryAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Subscription)
admin.site.register(User)
admin.site.register(Group)
admin.site.register(Site)
