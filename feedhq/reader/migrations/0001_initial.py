# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings
import django.utils.timezone
import feedhq.reader.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthToken',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('token', models.CharField(unique=True, verbose_name='Token', default=feedhq.reader.models.default_token, max_length=300, db_index=True)),
                ('date_created', models.DateTimeField(verbose_name='Creation date', default=django.utils.timezone.now)),
                ('client', models.CharField(blank=True, verbose_name='Client', max_length=1023)),
                ('user_agent', models.TextField(blank=True, verbose_name='User-Agent')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='auth_tokens', verbose_name='User', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('-date_created',),
            },
        ),
    ]
