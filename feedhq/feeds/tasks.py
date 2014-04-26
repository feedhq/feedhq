import logging
import requests

from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from django_push.subscriber.models import Subscription
from rache import schedule_job
from rq.timeouts import JobTimeoutException

from .. import es
from ..profiles.models import User
from ..utils import get_redis_connection

logger = logging.getLogger(__name__)


# TODO remove unused request_timeout
def update_feed(url, etag=None, modified=None, subscribers=1,
                request_timeout=10, backoff_factor=1, error=None, link=None,
                title=None, hub=None):
    from .models import UniqueFeed
    try:
        UniqueFeed.objects.update_feed(
            url, etag=etag, last_modified=modified, subscribers=subscribers,
            backoff_factor=backoff_factor, previous_error=error, link=link,
            title=title, hub=hub)
    except JobTimeoutException:
        backoff_factor = min(UniqueFeed.MAX_BACKOFF,
                             backoff_factor + 1)
        logger.debug("Job timed out, backing off %s to %s" % (
            url, backoff_factor,
        ))
        schedule_job(url, schedule_in=UniqueFeed.delay(backoff_factor),
                     backoff_factor=backoff_factor,
                     connection=get_redis_connection())


def read_later(user_id, entry_pk, use_es):
    from .models import Entry
    if use_es:
        user = User.objects.get(pk=user_id)
        entry = es.entry(user, entry_pk, annotate_results=False)
        entry.user = user
    else:
        entry = Entry.objects.get(pk=entry_pk)
    entry.read_later()


def update_favicon(feed_url, force_update=False):
    from .models import Favicon
    Favicon.objects.update_favicon(feed_url, force_update=force_update)


def ensure_subscribed(topic_url, hub_url):
    """Makes sure the PubSubHubbub subscription is verified"""
    if settings.TESTS:
        if str(type(requests.post)) != "<class 'mock.MagicMock'>":
            raise ValueError("Not Mocked")

    if hub_url is None:
        return

    call, args = None, ()
    try:
        s = Subscription.objects.get(topic=topic_url, hub=hub_url)
    except Subscription.DoesNotExist:
        logger.debug(u"Subscribing to {0} via {1}".format(topic_url, hub_url))
        call = Subscription.objects.subscribe
        args = topic_url, hub_url
    else:
        if (
            not s.verified or
            s.lease_expiration < timezone.now() + timedelta(days=1)
        ):
            logger.debug(u"Renewing subscription {0}".format(s.pk))
            call = s.subscribe
    if call is not None:
        call(*args)


def should_skip(date, ttl):
    delta = timedelta(days=ttl)
    return date + delta < timezone.now()


def store_entries(feed_url, entries):
    from .models import Entry, Feed

    feeds = Feed.objects.select_related('user').filter(
        url=feed_url, user__is_suspended=False).values('pk', 'user_id',
                                                       'category_id',
                                                       'user__es', 'user__ttl')

    guids = set([entry['guid'] for entry in entries])

    query = Q(feed__url=feed_url)
    es_query = [{'or': [{'term': {'feed': feed['pk']}} for feed in feeds]}]

    # When we have dates, filter the query to avoid returning the whole dataset
    date_generated = any([e.pop('date_generated') for e in entries])
    if not date_generated:
        earliest = min([entry['date'] for entry in entries])
        limit = earliest - timedelta(days=1)
        query &= Q(date__gte=limit)
        es_query.append({'range': {'timestamp': {'gt': limit}}})

    filter_by_title = len(guids) == 1 and len(entries) > 1
    if filter_by_title:
        # All items have the same guid. Query by title instead.
        titles = set([entry['title'] for entry in entries])
        query &= Q(title__in=titles)
        es_query.append({'or': [{'term': {'raw_title': t}} for t in titles]})
    else:
        query &= Q(guid__in=guids)
        es_query.append({'or': [{'term': {'guid': g}} for g in guids]})

    existing = Entry.objects.filter(query).values('guid', 'title', 'feed_id')

    indices = []
    for feed in feeds:
        if feed['user__es']:
            indices.append(es.user_index(feed['user_id']))

    if indices:
        es.wait_for_yellow()
        # Make sure guid and raw_title are not analyzed before querying
        # anything. Otherwise existing entries are never matched and things
        # keep being inserted.
        mappings = es.client.indices.get_field_mapping(index=",".join(indices),
                                                       doc_type='entries',
                                                       field='guid,raw_title')
        for idx, mapping in mappings.items():
            mapping = mapping['mappings']['entries']
            for f in ['raw_title', 'guid']:
                assert mapping[f]['mapping'][f]['index'] == 'not_analyzed'
        existing_es = es.client.search(
            index=",".join(indices),
            doc_type='entries',
            body={
                'aggs': {
                    'existing': {
                        'filter': {'and': es_query},
                        'aggs': {
                            'feeds': {
                                'terms': {'field': 'feed', 'size': 0},
                                'aggs': {
                                    'guids': {'terms': {'field': 'guid',
                                                        'size': 0}},
                                    'titles': {'terms': {'field': 'raw_title',
                                                         'size': 0}},
                                },
                            },
                        },
                    },
                },
            },
        )
        existing_es = existing_es[
            'aggregations']['existing']['feeds']['buckets']
    else:
        existing_es = []

    existing_guids = defaultdict(set)
    existing_titles = defaultdict(set)
    for entry in existing:
        existing_guids[entry['feed_id']].add(entry['guid'])
        if filter_by_title:
            existing_titles[entry['feed_id']].add(entry['title'])

    existing_es_guids = defaultdict(set)
    existing_es_titles = defaultdict(set)
    for bucket in existing_es:
        for sub in bucket['guids']['buckets']:
            existing_es_guids[bucket['key']].add(sub['key'])
        if filter_by_title:
            for sub in bucket['titles']['buckets']:
                existing_es_titles[bucket['key']].add(sub['key'])

    create = []
    ops = []
    update_unread_counts = set()
    refresh_updates = defaultdict(list)
    for feed in feeds:
        if feed['user__es']:
            index_name = es.user_index(feed['user_id'])
            for entry in entries:
                if (
                    not filter_by_title and
                    entry['guid'] in existing_es_guids[feed['pk']]
                ):
                    continue
                if (
                    filter_by_title and
                    entry['title'] in existing_es_titles[feed['pk']]
                ):
                    continue
                if (
                    feed['user__ttl'] and
                    should_skip(entry['date'], feed['user__ttl'])
                ):
                    continue
                data = Entry(**entry).serialize()
                data['category'] = feed['category_id']
                data['feed'] = feed['pk']
                data['_id'] = es.next_id()
                data['_type'] = 'entries'
                data['_index'] = index_name
                ops.append(data)
                refresh_updates[feed['user_id']].append(entry['date'])
        else:
            for entry in entries:
                if (
                    not filter_by_title and
                    entry['guid'] in existing_guids[feed['pk']]
                ):
                    continue
                if (
                    filter_by_title and
                    entry['title'] in existing_titles[feed['pk']]
                ):
                    continue
                if (
                    feed['user__ttl'] and
                    should_skip(entry['date'], feed['user__ttl'])
                ):
                    continue
                create.append(Entry(user_id=feed['user_id'],
                                    feed_id=feed['pk'], **entry))
                update_unread_counts.add(feed['pk'])
                refresh_updates[feed['user_id']].append(entry['date'])

    if create:
        Entry.objects.bulk_create(create)

    if ops:
        es.bulk(ops, raise_on_error=True)

        if settings.TESTS:
            # Indices are refreshed asynchronously. Refresh immediately
            # during tests.
            indices = ",".join(set([doc['_index'] for doc in ops]))
            es.client.indices.refresh(indices)

    for pk in update_unread_counts:
        Feed.objects.filter(pk=pk).update(
            unread_count=Entry.objects.filter(feed_id=pk, read=False).count())

    redis = get_redis_connection()
    for user_id, dates in refresh_updates.items():
        user = User(pk=user_id)
        new_score = float(max(dates).strftime('%s'))
        current_score = redis.zscore(user.last_update_key, feed_url) or 0
        if new_score > current_score:
            redis.zadd(user.last_update_key, feed_url, new_score)
