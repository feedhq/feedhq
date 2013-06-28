import json
import math

from django.conf.urls import url, patterns
from django.contrib.admin import widgets
from django.http import HttpResponse
from rache import scheduled_jobs
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
    list_display = ('truncated_url', 'last_update', 'muted', 'error',
                    'backoff_factor')
    list_filter = ('muted', 'error', 'backoff_factor')
    search_fields = ('url', 'title', 'link')

    class Media:
        js = (
            'feeds/js/d3.v3.min.js',
            'feeds/js/graph-scheduler.js',
        )

    def get_urls(self):
        return patterns(
            '',
            url(r'^graph/$', self.admin_site.admin_view(self.graph_data),
                name='graph-data'),
        ) + super(UniqueFeedAdmin, self).get_urls()

    def graph_data(self, request):
        jobs = list(scheduled_jobs(with_times=True))

        timespan = jobs[-1][1] - jobs[0][1]
        interval = math.ceil(timespan / 500)
        start = jobs[0][1]
        counts = [0]
        for url, time in jobs:
            while len(counts) * interval < time - start:
                counts.append(0)
            counts[-1] += 1

        return HttpResponse(json.dumps({'max': max(counts),
                                        'counts': counts,
                                        'timespan': timespan}))


class FeedAdmin(ModelAdmin):
    list_display = ('name', 'category', 'unread_count', 'favicon_img')
    search_fields = ('name', 'url')
    raw_id_fields = ('category', 'user')


class EntryAdmin(ModelAdmin):
    list_display = ('title', 'date')
    search_fields = ('title', 'link')
    raw_id_fields = ('feed', 'user')


class FaviconAdmin(ModelAdmin):
    list_display = ('url', 'favicon_img')
    search_fields = ('url',)


admin.site.register(Category, CategoryAdmin)
admin.site.register(UniqueFeed, UniqueFeedAdmin)
admin.site.register(Feed, FeedAdmin)
admin.site.register(Entry, EntryAdmin)
admin.site.register(Favicon, FaviconAdmin)
