# -*- coding: utf-8 -*-
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding field 'AuthToken.client'
        db.add_column(u'reader_authtoken', 'client',
                      self.gf('django.db.models.fields.CharField')(default='', max_length=1023, blank=True),
                      keep_default=False)

        # Adding field 'AuthToken.user_agent'
        db.add_column(u'reader_authtoken', 'user_agent',
                      self.gf('django.db.models.fields.TextField')(default='', blank=True),
                      keep_default=False)


        # Changing field 'AuthToken.user'
        db.alter_column(u'reader_authtoken', 'user_id', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['profiles.User']))

    def backwards(self, orm):
        # Deleting field 'AuthToken.client'
        db.delete_column(u'reader_authtoken', 'client')

        # Deleting field 'AuthToken.user_agent'
        db.delete_column(u'reader_authtoken', 'user_agent')


        # Changing field 'AuthToken.user'
        db.alter_column(u'reader_authtoken', 'user_id', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['auth.User']))

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
        u'profiles.user': {
            'Meta': {'object_name': 'User', 'db_table': "'auth_user'"},
            'allow_media': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.CharField', [], {'max_length': '75'}),
            'entries_per_page': ('django.db.models.fields.IntegerField', [], {'default': '50'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
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
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': u"orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '75'})
        },
        u'reader.authtoken': {
            'Meta': {'ordering': "('-date_created',)", 'object_name': 'AuthToken'},
            'client': ('django.db.models.fields.CharField', [], {'max_length': '1023', 'blank': 'True'}),
            'date_created': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            u'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'token': ('django.db.models.fields.CharField', [], {'default': "u'x6zQyPtU4lYXTuplsLR57NBTWhjct4suFbUgGlPOfmCFFE1dcuAdazhrOYWNWn91AanAMrRrpozrLIsM6LlZK0Ho0VdhhLWnxXRSfnqz7bkHOzB0hdLfogjnpYTyB2cUTV94dRnQB0TS7CXSy4uAH90mVLBQ0MOqnGR216yjJmGTc4EL1Sow9FJxaW3Fi9SL3dyIudbSvrrByzL43SVL51qKeCfSAMs8CpwVNPSvCjwLblE42B2bcI8cX3sL9SzIfO7rRW9cUiH'", 'unique': 'True', 'max_length': '300', 'db_index': 'True'}),
            'user': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'auth_tokens'", 'to': u"orm['profiles.User']"}),
            'user_agent': ('django.db.models.fields.TextField', [], {'blank': 'True'})
        }
    }

    complete_apps = ['reader']