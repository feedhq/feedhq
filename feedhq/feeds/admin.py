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


class UniqueFeedAdmin(admin.ModelAdmin):
    list_display = ('url', 'subscribers', 'last_update', 'muted',
                    'muted_reason', 'failed_attempts')
    list_filter = ('muted', 'muted_reason', 'hub')
    search_fields = ('url', 'title', 'link')


class FeedAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'unread_count', 'favicon_img')
    search_fields = ('name', 'title', 'url')


class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'date')
    search_fields = ('title', 'link', 'permalink')


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
