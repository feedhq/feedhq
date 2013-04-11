# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'AuthToken'
        db.create_table(u'reader_authtoken', (
            (u'id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('user', self.gf('django.db.models.fields.related.ForeignKey')(related_name='auth_tokens', to=orm['auth.User'])),
            ('token', self.gf('django.db.models.fields.CharField')(default=u'VQnsWk6jSERysKWsV9iuzkcDIw28Qb4tapRkKSppUDMkSO1m1xJOFhVinPWqCWkF6XmlY0ETCAhuj3rK0KnnSKoLlHxYprrh6yrVBnQkbKWz4I6ha36GgJkrM6oiPYV5CJvdsVRPz2RMg5gBDAkfm86OYqZOX0Lsb0CtHW0pR7MIEHcrc0FXDdNJwMVjfZi0DqNucGXwvfxP4dUTHpu3e3i9fuUfVbMvh6ugfMR0md0bbieVU71WfLzNX1rQC1ODxw9Px7QLi3w', max_length=300, db_index=True)),
            ('date_created', self.gf('django.db.models.fields.DateTimeField')(default=datetime.datetime.now)),
        ))
        db.send_create_signal(u'reader', ['AuthToken'])


    def backwards(self, orm):
        # Deleting model 'AuthToken'
        db.delete_table(u'reader_authtoken')


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
        u'reader.authtoken': {
            'Meta': {'object_name': 'AuthToken'},
            'date_created': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'token': ('django.db.models.fields.CharField', [], {'default': "u'VQnsWk6jSERysKWsV9iuzkcDIw28Qb4tapRkKSppUDMkSO1m1xJOFhVinPWqCWkF6XmlY0ETCAhuj3rK0KnnSKoLlHxYprrh6yrVBnQkbKWz4I6ha36GgJkrM6oiPYV5CJvdsVRPz2RMg5gBDAkfm86OYqZOX0Lsb0CtHW0pR7MIEHcrc0FXDdNJwMVjfZi0DqNucGXwvfxP4dUTHpu3e3i9fuUfVbMvh6ugfMR0md0bbieVU71WfLzNX1rQC1ODxw9Px7QLi3w'", 'max_length': '300', 'db_index': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'auth_tokens'", 'to': u"orm['auth.User']"})
        }
    }

    complete_apps = ['reader']