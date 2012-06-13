from ratelimitbackend import admin

from django_push.subscriber.models import Subscription

from .models import Category, Feed, Entry, Favicon


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


class FeedAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'unread_count', 'favicon_img')
    search_fields = ('name', 'title', 'url')


class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'date')


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('topic', 'hub', 'verified', 'lease_expiration')
    list_filter = ('verified', 'hub')
    search_fields = ('topic', 'hub')


class FaviconAdmin(admin.ModelAdmin):
    list_display = ('url', 'favicon_img')


admin.site.register(Category, CategoryAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Favicon, FaviconAdmin)
admin.site.register(Subscription, SubscriptionAdmin)
