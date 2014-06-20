# -*- coding: utf-8 -*-
from django.conf import settings
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import DataMigration

from ... import es


class Migration(DataMigration):
    depends_on = (
        ('feeds', '0016_auto__add_index_feed_url'),
    )

    def forwards(self, orm):
        "Write your forwards methods here."
        # Note: Don't use "from appname.models import ModelName".
        # Use orm.ModelName to refer to models in this application,
        # and orm['appname.ModelName'] for models in other applications.
        for user in orm.User.objects.exclude(es=True):
            name = es.user_alias(user.pk)
            es.client.indices.put_alias(
                index=settings.ES_INDEX,
                name=name,
                body={
                    'routing': user.pk,
                    'filter': {'term': {'user': user.pk}},
                },
            )
            for feed in user.feeds.all():
                entries = feed.entries.all()
                docs = [doc.serialize() for doc in entries]
                if not docs:
                    continue
                es.bulk(docs, index=name, timeout=60, raise_on_error=True)
            user.es = True
            user.save(update_fields=['es'])
        db.execute('alter sequence feeds_entry_id_seq owned by none')
        db.execute('truncate feeds_entry')

    def backwards(self, orm):
        "Write your backwards methods here."

    models = {
        u'auth.group': {
            'Meta': {'object_name': 'Group'},
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        u'auth.permission': {
            'Meta': {'ordering': "(u'content_type__app_label', u'content_type__model', u'codename')", 'unique_together': "((u'content_type', u'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': u"orm['contenttypes.ContentType']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        u'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        u'feeds.category': {
            'Meta': {'ordering': "('order', 'name', 'id')", 'unique_together': "(('user', 'slug'), ('user', 'name'))", 'object_name': 'Category'},
            'color': ('django.db.models.fields.CharField', [], {'default': "'blue'", 'max_length': '50'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '1023', 'db_index': 'True'}),
            'order': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'categories'", 'to': u"orm['profiles.User']"})
        },
        u'feeds.entry': {
            'Meta': {'ordering': "('-date', '-id')", 'object_name': 'Entry', 'index_together': "(('user', 'date'), ('user', 'read'), ('user', 'starred'), ('user', 'broadcast'))"},
            'author': ('django.db.models.fields.CharField', [], {'max_length': '1023', 'blank': 'True'}),
            'broadcast': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'date': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'feed': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'entries'", 'null': 'True', 'to': u"orm['feeds.Feed']"}),
            'guid': ('feedhq.feeds.fields.URLField', [], {'db_index': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'link': ('feedhq.feeds.fields.URLField', [], {'db_index': 'True'}),
            'read': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'read_later_url': ('feedhq.feeds.fields.URLField', [], {'blank': 'True'}),
            'starred': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'subtitle': ('django.db.models.fields.TextField', [], {}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'entries'", 'to': u"orm['profiles.User']"})
        },
        u'feeds.favicon': {
            'Meta': {'object_name': 'Favicon'},
            'favicon': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'url': ('feedhq.feeds.fields.URLField', [], {'unique': 'True', 'db_index': 'True'})
        },
        u'feeds.feed': {
            'Meta': {'ordering': "('name',)", 'object_name': 'Feed'},
            'category': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'feeds'", 'null': 'True', 'to': u"orm['feeds.Category']"}),
            'favicon': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'img_safe': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '1023'}),
            'unread_count': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'}),
            'url': ('feedhq.feeds.fields.URLField', [], {'db_index': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'feeds'", 'to': u"orm['profiles.User']"})
        },
        u'feeds.uniquefeed': {
            'Meta': {'object_name': 'UniqueFeed'},
            'error': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'db_column': "'muted_reason'", 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'muted': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'url': ('feedhq.feeds.fields.URLField', [], {'unique': 'True'})
        },
        u'profiles.user': {
            'Meta': {'object_name': 'User', 'db_table': "'auth_user'"},
            'allow_media': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.CharField', [], {'max_length': '75'}),
            'endless_pages': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'entries_per_page': ('django.db.models.fields.IntegerField', [], {'default': '50'}),
            'es': ('django.db.models.fields.NullBooleanField', [], {'default': 'True', 'null': 'True', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30'}),
            'font': ('django.db.models.fields.CharField', [], {'default': "'pt-serif'", 'max_length': '75'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Group']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_suspended': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30'}),
            'oldest_first': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'read_later': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'read_later_credentials': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'sharing_email': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'sharing_gplus': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'sharing_twitter': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'timezone': ('django.db.models.fields.CharField', [], {'default': "'UTC'", 'max_length': '75'}),
            'ttl': ('django.db.models.fields.PositiveIntegerField', [], {'default': '30'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'related_name': "u'user_set'", 'blank': 'True', 'to': u"orm['auth.Permission']"}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '75'})
        }
    }

    complete_apps = ['feeds']
    symmetrical = True
