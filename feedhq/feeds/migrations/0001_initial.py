# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import feedhq.storage
import feedhq.feeds.models
import feedhq.feeds.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(verbose_name='Name', db_index=True, max_length=1023)),
                ('slug', models.SlugField(verbose_name='Slug')),
                ('order', models.PositiveIntegerField(null=True, blank=True)),
                ('color', models.CharField(default=feedhq.feeds.models.random_color, max_length=50, verbose_name='Color', choices=[('red', 'Red'), ('dark-red', 'Dark Red'), ('pale-green', 'Pale Green'), ('green', 'Green'), ('army-green', 'Army Green'), ('pale-blue', 'Pale Blue'), ('blue', 'Blue'), ('dark-blue', 'Dark Blue'), ('orange', 'Orange'), ('dark-orange', 'Dark Orange'), ('black', 'Black'), ('gray', 'Gray')])),
            ],
            options={
                'ordering': ('order', 'name', 'id'),
                'verbose_name_plural': 'categories',
            },
        ),
        migrations.CreateModel(
            name='Entry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('title', models.CharField(verbose_name='Title', max_length=255)),
                ('subtitle', models.TextField(verbose_name='Abstract')),
                ('link', feedhq.feeds.fields.URLField(verbose_name='URL', db_index=True)),
                ('author', models.CharField(verbose_name='Author', max_length=1023, blank=True)),
                ('date', models.DateTimeField(verbose_name='Date', db_index=True)),
                ('guid', feedhq.feeds.fields.URLField(verbose_name='GUID', db_index=True, blank=True)),
                ('read', models.BooleanField(default=False, db_index=True, verbose_name='Read')),
                ('read_later_url', feedhq.feeds.fields.URLField(verbose_name='Read later URL', blank=True)),
                ('starred', models.BooleanField(default=False, db_index=True, verbose_name='Starred')),
                ('broadcast', models.BooleanField(default=False, db_index=True, verbose_name='Broadcast')),
            ],
            options={
                'ordering': ('-date', '-id'),
                'verbose_name_plural': 'entries',
            },
            bases=(feedhq.feeds.models.BaseEntry, models.Model),
        ),
        migrations.CreateModel(
            name='Favicon',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('url', feedhq.feeds.fields.URLField(unique=True, verbose_name='URL', db_index=True)),
                ('favicon', models.FileField(storage=feedhq.storage.OverwritingStorage(), upload_to='favicons', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Feed',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(verbose_name='Name', max_length=1023)),
                ('url', feedhq.feeds.fields.URLField(verbose_name='URL', db_index=True)),
                ('favicon', models.ImageField(verbose_name='Favicon', null=True, upload_to='favicons', storage=feedhq.storage.OverwritingStorage(), blank=True)),
                ('img_safe', models.BooleanField(default=False, verbose_name='Display images by default')),
                ('category', models.ForeignKey(help_text='<a href="/category/add/">Add a category</a>', related_name='feeds', blank=True, to='feeds.Category', null=True, verbose_name='Category', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('name',),
            },
            bases=(feedhq.feeds.models.JobDataMixin, models.Model),
        ),
        migrations.CreateModel(
            name='UniqueFeed',
            fields=[
                ('id', models.AutoField(verbose_name='ID', auto_created=True, primary_key=True, serialize=False)),
                ('url', feedhq.feeds.fields.URLField(unique=True, verbose_name='URL')),
                ('muted', models.BooleanField(default=False, db_index=True, verbose_name='Muted')),
                ('error', models.CharField(max_length=50, db_column='muted_reason', null=True, verbose_name='Error', blank=True, choices=[('gone', 'Feed gone (410)'), ('timeout', 'Feed timed out'), ('parseerror', 'Location parse error'), ('connerror', 'Connection error'), ('decodeerror', 'Decoding error'), ('notafeed', 'Not a valid RSS/Atom feed'), ('400', 'HTTP 400'), ('401', 'HTTP 401'), ('403', 'HTTP 403'), ('404', 'HTTP 404'), ('500', 'HTTP 500'), ('502', 'HTTP 502'), ('503', 'HTTP 503')])),
            ],
            bases=(feedhq.feeds.models.JobDataMixin, models.Model),
        ),
    ]
