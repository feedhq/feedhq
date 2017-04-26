from collections import defaultdict
from datetime import timedelta

import requests
import structlog
from django.conf import settings
from django.utils import timezone
from django_push.subscriber.models import Subscription, SubscriptionError
from rache import schedule_job
from rq.timeouts import JobTimeoutException

from .. import es
from ..profiles.models import User
from ..utils import get_redis_connection

logger = structlog.get_logger(__name__)


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
        logger.info("job timed out, backing off",
                    url=url, backoff_factor=backoff_factor)
        schedule_job(url, schedule_in=UniqueFeed.delay(backoff_factor),
                     backoff_factor=backoff_factor,
                     connection=get_redis_connection())
    except BaseException as e:
        logger.info("fatal job exception", url=url, exc_info=e)
        raise


def read_later(user_id, entry_pk):
    user = User.objects.get(pk=user_id)
    entry = es.entry(user, entry_pk, annotate_results=False)
    entry.user = user
    entry.read_later()


def update_favicon(feed_url, force_update=False):
    from .models import Favicon
    Favicon.objects.update_favicon(feed_url, force_update=force_update)


def ensure_subscribed(topic_url, hub_url):
    """Makes sure the PubSubHubbub subscription is verified"""
    if settings.TESTS:
        if str(type(requests.post)) != "<class 'unittest.mock.MagicMock'>":
            raise ValueError("Not Mocked")

    if hub_url is None:
        return

    log = logger.bind(topic_url=topic_url, hub_url=hub_url)

    call, args = None, ()
    try:
        s = Subscription.objects.get(topic=topic_url, hub=hub_url)
    except Subscription.DoesNotExist:
        log.info("subscribing")
        call = Subscription.objects.subscribe
        args = topic_url, hub_url
    else:
        if (
            not s.verified or
            s.lease_expiration < timezone.now() + timedelta(days=1)
        ):
            log.info("renewing subscription", subscription=s.pk)
            call = s.subscribe
    if call is not None:
        try:
            call(*args)
        except SubscriptionError as e:
            log.info("subscription error", exc_info=e, subscription=s.pk)


def should_skip(date, ttl):
    delta = timedelta(days=ttl)
    return date + delta < timezone.now()


def store_entries(feed_url, entries):
    from .models import Entry, Feed

    feeds = Feed.objects.select_related('user').filter(
        url=feed_url, user__is_suspended=False).values('pk', 'user_id',
                                                       'category_id',
                                                       'user__ttl')

    guids = set([entry['guid'] for entry in entries])

    es_query = [{'or': [{'term': {'feed': feed['pk']}} for feed in feeds]}]

    # When we have dates, filter the query to avoid returning the whole dataset
    date_generated = any([e.pop('date_generated') for e in entries])
    if not date_generated:
        earliest = min([entry['date'] for entry in entries])
        limit = earliest - timedelta(days=1)
        es_query.append({'range': {'timestamp': {'gt': limit}}})

    filter_by_title = len(guids) == 1 and len(entries) > 1
    if filter_by_title:
        # All items have the same guid. Query by title instead.
        titles = set([entry['title'] for entry in entries])
        es_query.append({'or': [{'term': {'raw_title': t}} for t in titles]})
    else:
        es_query.append({'or': [{'term': {'guid': g}} for g in guids]})

    existing = None

    indices = []
    for feed in feeds:
        indices.append(es.user_alias(feed['user_id']))

    if indices:
        es.wait_for_yellow()
        # Make sure guid and raw_title are not analyzed before querying
        # anything. Otherwise existing entries are never matched and things
        # keep being inserted.
        mappings = es.client.indices.get_field_mapping(index=",".join(indices),
                                                       doc_type='entries',
                                                       field='guid,raw_title')
        for mapping in mappings.values():
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
    if existing is not None:
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

    ops = []
    refresh_updates = defaultdict(list)
    for feed in feeds:
        seen_guids = set()
        seen_titles = set()
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

            if filter_by_title and entry['title'] in seen_titles:
                continue
            seen_titles.add(entry['title'])

            if not filter_by_title and entry['guid'] in seen_guids:
                continue
            seen_guids.add(entry['guid'])

            data = Entry(**entry).serialize()
            data['category'] = feed['category_id']
            data['feed'] = feed['pk']
            data['_id'] = es.next_id()
            data['id'] = data['_id']
            data['_type'] = 'entries'
            data['user'] = feed['user_id']
            data['_index'] = settings.ES_INDEX
            ops.append(data)
            refresh_updates[feed['user_id']].append(entry['date'])

    if ops:
        es.bulk(ops, raise_on_error=True)

        if settings.TESTS:
            # Indices are refreshed asynchronously. Refresh immediately
            # during tests.
            indices = ",".join(set([doc['_index'] for doc in ops]))
            es.client.indices.refresh(indices)

    redis = get_redis_connection()
    for user_id, dates in refresh_updates.items():
        user = User(pk=user_id)
        new_score = float(max(dates).strftime('%s'))
        current_score = redis.zscore(user.last_update_key, feed_url) or 0
        if new_score > current_score:
            redis.zadd(user.last_update_key, feed_url, new_score)
