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
    search_fields = ('name', 'title', 'url')


class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'user')


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('topic', 'hub', 'verified', 'lease_expiration')
    list_filter = ('verified', 'hub')
    search_fields = ('topic', 'hub')


admin.site.register(Category, CategoryAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(User)
admin.site.register(Group)
admin.site.register(Site)
