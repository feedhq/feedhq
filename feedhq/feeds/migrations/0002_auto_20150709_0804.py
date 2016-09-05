# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('feeds', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='feed',
            name='user',
            field=models.ForeignKey(related_name='feeds', to=settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='entry',
            name='feed',
            field=models.ForeignKey(related_name='entries', to='feeds.Feed', blank=True, null=True, verbose_name='Feed', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='entry',
            name='user',
            field=models.ForeignKey(related_name='entries', to=settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='category',
            name='user',
            field=models.ForeignKey(related_name='categories', to=settings.AUTH_USER_MODEL, verbose_name='User', on_delete=models.CASCADE),
        ),
        migrations.AlterIndexTogether(
            name='entry',
            index_together=set([('user', 'broadcast'), ('user', 'read'), ('user', 'date'), ('user', 'starred')]),
        ),
        migrations.AlterUniqueTogether(
            name='category',
            unique_together=set([('user', 'name'), ('user', 'slug')]),
        ),
    ]
