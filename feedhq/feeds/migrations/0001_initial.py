# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'Category'
        db.create_table(u'feeds_category', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=1023)),
            ('slug', self.gf('django.db.models.fields.SlugField')(max_length=50)),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(related_name='categories', to=orm['auth.User'])),
            ('order', self.gf('django.db.models.fields.PositiveIntegerField')(null=True, blank=True)),
            ('color', self.gf('django.db.models.fields.CharField')(default='dark-orange', max_length=50)),
        ))
        db.send_create_signal(u'feeds', ['Category'])

        # Adding model 'UniqueFeed'
        db.create_table(u'feeds_uniquefeed', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.URLField')(unique=True, max_length=1023)),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=2048, blank=True)),
            ('link', self.gf('django.db.models.fields.URLField')(max_length=2048, blank=True)),
            ('etag', self.gf('django.db.models.fields.CharField')(max_length=1023, null=True, blank=True)),
            ('modified', self.gf('django.db.models.fields.CharField')(max_length=1023, null=True, blank=True)),
            ('last_update', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now, db_index=True)),
            ('muted', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
            ('error', self.gf('django.db.models.fields.CharField')(max_length=50, null=True, db_column='muted_reason', blank=True)),
            ('hub', self.gf('django.db.models.fields.URLField')(max_length=1023, null=True, blank=True)),
            ('backoff_factor', self.gf('django.db.models.fields.PositiveIntegerField')(default=1)),
            ('last_loop', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now, db_index=True)),
            ('subscribers', self.gf('django.db.models.fields.PositiveIntegerField')(default=1, db_index=True)),
        ))
        db.send_create_signal(u'feeds', ['UniqueFeed'])

        # Adding model 'Feed'
        db.create_table(u'feeds_feed', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=255)),
            ('url', self.gf('django.db.models.fields.URLField')(max_length=1023)),
            ('category', self.gf('django.db.models.fields.related.ForeignKey')(related_name='feeds', to=orm['feeds.Category'])),
            ('unread_count', self.gf('django.db.models.fields.PositiveIntegerField')(default=0)),
            ('favicon', self.gf('django.db.models.fields.files.ImageField')(max_length=100, null=True)),
            ('img_safe', self.gf('django.db.models.fields.BooleanField')(default=False)),
        ))
        db.send_create_signal(u'feeds', ['Feed'])

        # Adding model 'Entry'
        db.create_table(u'feeds_entry', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('feed', self.gf('django.db.models.fields.related.ForeignKey')(related_name='entries', to=orm['feeds.Feed'])),
            ('title', self.gf('django.db.models.fields.CharField')(max_length=255)),
            ('subtitle', self.gf('django.db.models.fields.TextField')()),
            ('link', self.gf('django.db.models.fields.URLField')(max_length=1023)),
            ('permalink', self.gf('django.db.models.fields.URLField')(max_length=1023, blank=True)),
            ('date', self.gf('django.db.models.fields.DateTimeField')(db_index=True)),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(related_name='entries', to=orm['auth.User'])),
            ('read', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
            ('read_later_url', self.gf('django.db.models.fields.URLField')(max_length=1023, blank=True)),
            ('starred', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
            ('broadcast', self.gf('django.db.models.fields.BooleanField')(default=False, db_index=True)),
        ))
        db.send_create_signal(u'feeds', ['Entry'])

        # Adding model 'Favicon'
        db.create_table(u'feeds_favicon', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.URLField')(unique=True, max_length=2048, db_index=True)),
            ('favicon', self.gf('django.db.models.fields.files.FileField')(max_length=100, blank=True)),
        ))
        db.send_create_signal(u'feeds', ['Favicon'])


    def backwards(self, orm):
        # Deleting model 'Category'
        db.delete_table(u'feeds_category')

        # Deleting model 'UniqueFeed'
        db.delete_table(u'feeds_uniquefeed')

        # Deleting model 'Feed'
        db.delete_table(u'feeds_feed')

        # Deleting model 'Entry'
        db.delete_table(u'feeds_entry')

        # Deleting model 'Favicon'
        db.delete_table(u'feeds_favicon')


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
        u'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'entries_per_page': ('django.db.models.fields.IntegerField', [], {'default': '50'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'read_later': ('django.db.models.fields.CharField', [], {'max_length': '50', 'blank': 'True'}),
            'read_later_credentials': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'sharing_email': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'sharing_gplus': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'sharing_twitter': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'timezone': ('django.db.models.fields.CharField', [], {'default': "'UTC'", 'max_length': '75'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '75'})
        },
        u'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        u'feeds.category': {
            'Meta': {'ordering': "('order', 'name', 'id')", 'object_name': 'Category'},
            'color': ('django.db.models.fields.CharField', [], {'default': "'red'", 'max_length': '50'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '1023'}),
            'order': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True', 'blank': 'True'}),
            'slug': ('django.db.models.fields.SlugField', [], {'max_length': '50'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'categories'", 'to': u"orm['auth.User']"})
        },
        u'feeds.entry': {
            'Meta': {'ordering': "('-date', 'title')", 'object_name': 'Entry'},
            'broadcast': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'date': ('django.db.models.fields.DateTimeField', [], {'db_index': 'True'}),
            'feed': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'entries'", 'to': u"orm['feeds.Feed']"}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'link': ('django.db.models.fields.URLField', [], {'max_length': '1023'}),
            'permalink': ('django.db.models.fields.URLField', [], {'max_length': '1023', 'blank': 'True'}),
            'read': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'read_later_url': ('django.db.models.fields.URLField', [], {'max_length': '1023', 'blank': 'True'}),
            'starred': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'subtitle': ('django.db.models.fields.TextField', [], {}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'entries'", 'to': u"orm['auth.User']"})
        },
        u'feeds.favicon': {
            'Meta': {'object_name': 'Favicon'},
            'favicon': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'url': ('django.db.models.fields.URLField', [], {'unique': 'True', 'max_length': '2048', 'db_index': 'True'})
        },
        u'feeds.feed': {
            'Meta': {'ordering': "('name',)", 'object_name': 'Feed'},
            'category': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'feeds'", 'to': u"orm['feeds.Category']"}),
            'favicon': ('django.db.models.fields.files.ImageField', [], {'max_length': '100', 'null': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'img_safe': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255'}),
            'unread_count': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'}),
            'url': ('django.db.models.fields.URLField', [], {'max_length': '1023'})
        },
        u'feeds.uniquefeed': {
            'Meta': {'object_name': 'UniqueFeed'},
            'backoff_factor': ('django.db.models.fields.PositiveIntegerField', [], {'default': '1'}),
            'error': ('django.db.models.fields.CharField', [], {'max_length': '50', 'null': 'True', 'db_column': "'muted_reason'", 'blank': 'True'}),
            'etag': ('django.db.models.fields.CharField', [], {'max_length': '1023', 'null': 'True', 'blank': 'True'}),
            'hub': ('django.db.models.fields.URLField', [], {'max_length': '1023', 'null': 'True', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'last_loop': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'db_index': 'True'}),
            'last_update': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'db_index': 'True'}),
            'link': ('django.db.models.fields.URLField', [], {'max_length': '2048', 'blank': 'True'}),
            'modified': ('django.db.models.fields.CharField', [], {'max_length': '1023', 'null': 'True', 'blank': 'True'}),
            'muted': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'db_index': 'True'}),
            'subscribers': ('django.db.models.fields.PositiveIntegerField', [], {'default': '1', 'db_index': 'True'}),
            'title': ('django.db.models.fields.CharField', [], {'max_length': '2048', 'blank': 'True'}),
            'url': ('django.db.models.fields.URLField', [], {'unique': 'True', 'max_length': '1023'})
        }
    }

    complete_apps = ['feeds']