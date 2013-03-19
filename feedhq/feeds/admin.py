from ratelimitbackend import admin

from django_push.subscriber.models import Subscription

from .models import Category, UniqueFeed, Feed, Entry, Favicon


class FeedInline(admin.TabularInline):
    model = Feed


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        (None, {
            'fields': (('name', 'slug'), 'user', 'order'),
        }),
    )
    inlines = [FeedInline]
    raw_id_fields = ('user',)


class UniqueFeedAdmin(admin.ModelAdmin):
    list_display = ('url', 'last_update', 'muted', 'error', 'backoff_factor')
    list_filter = ('muted', 'error', 'backoff_factor')
    search_fields = ('url', 'title', 'link')


class FeedAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'unread_count', 'favicon_img')
    search_fields = ('name', 'url')
    raw_id_fields = ('category',)


class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'date')
    search_fields = ('title', 'link', 'permalink')
    raw_id_fields = ('feed', 'user')


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('topic', 'hub', 'verified', 'lease_expiration')
    list_filter = ('verified', 'hub')
    search_fields = ('topic', 'hub')


class FaviconAdmin(admin.ModelAdmin):
    list_display = ('url', 'favicon_img')
    search_fields = ('url',)


admin.site.register(Category, CategoryAdmin)
admin.site.register(UniqueFeed, UniqueFeedAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Favicon, FaviconAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
