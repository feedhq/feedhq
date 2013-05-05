from django.contrib.admin import widgets
from django_push.subscriber.models import Subscription
from ratelimitbackend import admin

from .fields import URLField
from .models import Category, UniqueFeed, Feed, Entry, Favicon


class URLOverrideMixin(object):
    formfield_overrides = {
        URLField: {'widget': widgets.AdminURLFieldWidget},
    }


class TabularInline(URLOverrideMixin, admin.TabularInline):
    pass


class ModelAdmin(URLOverrideMixin, admin.ModelAdmin):
    pass


class FeedInline(TabularInline):
    model = Feed
    raw_id_fields = ('user',)


class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {
            'fields': (('name', 'slug'), 'user', 'order'),
        }),
    )
    inlines = [FeedInline]
    raw_id_fields = ('user',)


class UniqueFeedAdmin(ModelAdmin):
    list_display = ('url', 'last_update', 'muted', 'error', 'backoff_factor')
    list_filter = ('muted', 'error', 'backoff_factor')
    search_fields = ('url', 'title', 'link')


class FeedAdmin(ModelAdmin):
    list_display = ('name', 'category', 'unread_count', 'favicon_img')
    search_fields = ('name', 'url')
    raw_id_fields = ('category', 'user')


class EntryAdmin(ModelAdmin):
    list_display = ('title', 'date')
    search_fields = ('title', 'link')
    raw_id_fields = ('feed', 'user')


class SubscriptionAdmin(ModelAdmin):
    list_display = ('topic', 'hub', 'verified', 'lease_expiration')
    list_filter = ('verified', 'hub')
    search_fields = ('topic', 'hub')


class FaviconAdmin(ModelAdmin):
    list_display = ('url', 'favicon_img')
    search_fields = ('url',)


admin.site.register(Category, CategoryAdmin)
admin.site.register(UniqueFeed, UniqueFeedAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Favicon, FaviconAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
