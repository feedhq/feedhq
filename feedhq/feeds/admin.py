import json
import math

from django.conf.urls import url
from django.contrib.admin import widgets
from django.http import HttpResponse
from rache import scheduled_jobs
from ratelimitbackend import admin

from .fields import URLField
from .models import Category, Entry, Favicon, Feed, UniqueFeed
from ..utils import get_redis_connection


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
    list_display = ('truncated_url', 'last_update', 'muted', 'error')
    list_filter = ('muted', 'error')
    search_fields = ('url',)

    class Media:
        js = (
            'feeds/js/d3.v3.min.js',
            'feeds/js/graph-scheduler.js',
        )

    def get_urls(self):
        return [
            url(r'^graph/$', self.admin_site.admin_view(self.graph_data),
                name='graph-data'),
        ] + super().get_urls()

    def graph_data(self, request):
        jobs = list(scheduled_jobs(with_times=True,
                                   connection=get_redis_connection()))

        timespan = jobs[-1][1] - jobs[0][1]
        interval = math.ceil(timespan / 500)
        start = jobs[0][1]
        counts = [0]
        for _url, time in jobs:
            while len(counts) * interval < time - start:
                counts.append(0)
            counts[-1] += 1

        return HttpResponse(json.dumps({'max': max(counts),
                                        'counts': counts,
                                        'timespan': timespan}))


class FeedAdmin(ModelAdmin):
    list_display = ('name', 'category', 'favicon_img')
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
