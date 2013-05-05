import datetime
import random

from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from factory import (DjangoModelFactory as Factory, SubFactory, Sequence,
                     lazy_attribute)

from feedhq.feeds.models import Category, Feed, Entry


class UserFactory(Factory):
    FACTORY_FOR = User

    username = Sequence(lambda n: u'user{0}'.format(n))
    password = 'test'

    @lazy_attribute
    def email(self):
        return "{0}@example.com".format(self.username)

    @classmethod
    def _prepare(cls, create, **kwargs):
        if create:
            return User.objects.create_user(**kwargs)
        else:
            return super(UserFactory, cls)._prepare(create, **kwargs)


class CategoryFactory(Factory):
    FACTORY_FOR = Category

    name = Sequence(lambda n: u'Category {0}'.format(n))
    user = SubFactory(UserFactory)

    @lazy_attribute
    def slug(self):
        return slugify(self.name)


class FeedFactory(Factory):
    FACTORY_FOR = Feed

    name = Sequence(lambda n: u'Feed {0}'.format(n))
    url = Sequence(lambda n: u'http://example.com/feeds/{0}'.format(n))
    category = SubFactory(CategoryFactory)
    user = SubFactory(UserFactory)


class EntryFactory(Factory):
    FACTORY_FOR = Entry

    feed = SubFactory(FeedFactory)
    title = Sequence(lambda n: u'Entry {0}'.format(n))
    subtitle = 'dummy content'
    link = Sequence(lambda n: u'https://example.com/entry/{0}'.format(n))
    user = SubFactory(UserFactory)

    @lazy_attribute
    def date(self):
        minutes = random.randint(0, 60*24*2)  # 2 days
        return timezone.now() - datetime.timedelta(minutes=minutes)
