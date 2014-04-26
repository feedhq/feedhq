# -*- coding: utf-8 -*-
import datetime
import random

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify, force_text
from factory import (DjangoModelFactory as Factory, SubFactory, Sequence,
                     lazy_attribute)

from feedhq.feeds.models import Category, Feed, Entry
from feedhq.profiles.models import User


class UserFactory(Factory):
    FACTORY_FOR = User

    username = Sequence(lambda n: u'ùser{0}'.format(n))
    password = 'test'
    es = settings.USE_ES

    @lazy_attribute
    def email(self):
        return u"{0}@example.com".format(slugify(force_text(self.username)))

    @classmethod
    def _prepare(cls, create, **kwargs):
        if create:
            return User.objects.create_user(**kwargs)
        else:
            return super(UserFactory, cls)._prepare(create, **kwargs)


class CategoryFactory(Factory):
    FACTORY_FOR = Category

    name = Sequence(lambda n: u'Categorỳ {0}'.format(n))
    user = SubFactory(UserFactory)

    @lazy_attribute
    def slug(self):
        return slugify(self.name)


class FeedFactory(Factory):
    FACTORY_FOR = Feed

    name = Sequence(lambda n: u'Feèd {0}'.format(n))
    url = Sequence(lambda n: u'http://example.com/feèds/{0}'.format(n))
    category = SubFactory(CategoryFactory)
    user = SubFactory(UserFactory)


class EntryFactory(Factory):
    FACTORY_FOR = Entry

    feed = SubFactory(FeedFactory)
    title = Sequence(lambda n: u'Entrỳ {0}'.format(n))
    subtitle = 'dùmmy content'
    link = Sequence(lambda n: u'https://example.com/entrỳ/{0}'.format(n))
    user = SubFactory(UserFactory)

    @lazy_attribute
    def date(self):
        minutes = random.randint(0, 60*24*2)  # 2 days
        return timezone.now() - datetime.timedelta(minutes=minutes)

    @classmethod
    def create(cls, **kwargs):
        entry = super(EntryFactory, cls).create(**kwargs)
        if entry.user.es:
            new_entry = entry.index()
            new_entry.user = entry.user
            entry.delete()
            entry = new_entry
        return entry
