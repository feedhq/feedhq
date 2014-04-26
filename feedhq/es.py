from django.db import connection
from django.conf import settings
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk as es_bulk


client = Elasticsearch(settings.ES_NODES,
                       sniff_on_start=False,
                       sniff_on_connection_fail=True)


def user_index(user_id):
    assert isinstance(user_id, int), repr(user_id)
    return '{0}-{1}'.format(settings.ES_INDEX_PREFIX, user_id)


def wait_for_yellow():
    return client.cluster.health(wait_for_status='yellow')


def bulk(ops, **kwargs):
    """
    A wrapper for elasticsearch.helpers.bulk() that waits for a yellow
    cluster and uses our ES client.
    """
    wait_for_yellow()
    return es_bulk(client, ops, **kwargs)


def counts(user, feed_ids, only_unread=True):
    facets = {}
    for pk in feed_ids:
        term = {'term': {'feed': pk}}
        if only_unread:
            term = {'and': [
                {'term': {'read': False}},
                term,
            ]}
        facets[pk] = {
            'global': True,
            'filter': term,
        }
    query = {
        'facets': facets,
    }
    return client.search(index=user_index(user.pk),
                         doc_type='entries',
                         body=query,
                         params={'size': 0})['facets']


def entry(user, id, annotate_results=True):
    from .feeds.models import EsEntry
    result = client.get(user_index(user.pk), id)
    entry = EsEntry(result)
    if annotate_results:
        entry.user = user
        entry.feed = user.feeds.select_related('category').get(pk=entry.feed)
        if entry.category:
            entry.category = entry.feed.category
    return entry


def mget(user, pks, annotate_results=True):
    from .feeds.models import EsEntry
    docs = client.mget({'ids': pks}, index=user_index(user.pk),
                       doc_type='entries')['docs']
    results = []
    for doc in docs:
        if not doc['found']:
            continue
        doc['_id'] = int(doc['_id'])
        results.append(EsEntry(doc))
    if annotate_results:
        _annotate(results, user)
    return results


def entries(user, feed=None, category=None, query=None,
            only_unread=False, only_starred=False, only_broadcast=False,
            per_page=50, page=1, order='desc', terms=None,
            annotate_results=True, exclude=None, include=None,
            include_facets=True, date_gt=None, date_lt=None):
    from .feeds.models import EsEntry
    if query is None:
        query = {'match_all': {}}
    else:
        query = {'query_string': {'query': query}}

    manual_terms = terms
    terms = []
    if only_unread:
        terms.append({'term': {'read': False}})
    facets = {
        'unread': {
            'global': True,
            'filter': {'term': {'read': False}},
        },
    }
    if only_starred:
        terms.append({'term': {'starred': True}})
        facets['starred'] = {
            'global': True,
            'filter': {'term': {'starred': True}},
        }
        facets['starred_unread'] = {
            'global': True,
            'filter': {
                'and': [
                    {'term': {'starred': True}},
                    {'term': {'read': False}},
                ],
            },
        }
    if only_broadcast:
        terms.append({'term': {'broadcast': True}})
        facets['broadcast'] = {
            'global': True,
            'filter': {'term': {'broadcast': True}},
        }
    if feed is None and category is None:
        facets['all'] = {
            'global': True,
            'filter': {'match_all': {}},
        }
    if category is not None:
        terms.append({'term': {'category': category}})
        facets['category_all'] = {
            'global': True,
            'filter': {'term': {'category': category}},
        }
        facets['category_unread'] = {
            'global': True,
            'filter': {
                'and': [
                    {'term': {'category': category}},
                    {'term': {'read': False}},
                ],
            },
        }
    if feed is not None:
        terms.append({'term': {'feed': feed}})
        facets['feed_all'] = {
            'global': True,
            'filter': {'term': {'feed': feed}},
        }
        facets['feed_unread'] = {
            'global': True,
            'filter': {
                'and': [
                    {'term': {'feed': feed}},
                    {'term': {'read': False}},
                ],
            },
        }
    if date_lt is not None:
        terms.append({'range': {'timestamp': {'lt': date_lt}}})
    if date_gt is not None:
        terms.append({'range': {'timestamp': {'gt': date_gt}}})

    if exclude is None:
        exclude = []
    source = {
        'exclude': exclude,
    }
    if include is not None:
        source['include'] = include

    if manual_terms is not None:
        terms = manual_terms
    if terms:
        terms = {'and': terms}
    else:
        terms = {'match_all': {}}

    facets['query'] = {
        'global': True,
        'filter': terms
    }

    query = {
        '_source': source,
        'query': {
            'filtered': {
                'query': query,
                'filter': terms,
            },
        },
        'facets': facets,
    }
    if not include_facets:
        query.pop('facets')
    results = client.search(
        index=user_index(user.pk),
        doc_type='entries',
        body=query,
        params={
            'from': (page - 1) * per_page,
            'sort': 'timestamp:{0}'.format(order),
            'size': per_page,
        }
    )
    results['hits'] = [EsEntry(hit) for hit in results['hits']['hits']]
    if annotate_results:
        _annotate(results['hits'], user)
    return results


def _annotate(results, user):
    feed_ids = set([e.feed for e in results])
    if not feed_ids:
        return
    feeds = user.feeds.filter(pk__in=feed_ids).select_related('category')
    by_pk = {feed.pk: feed for feed in feeds}
    for entry in results:
        feed = by_pk[entry.feed]
        if getattr(entry, 'category', None):
            entry.category = feed.category
        entry.feed = feed
        entry.user = user


def next_id():
    cursor = connection.cursor()
    try:
        cursor.execute("select nextval('feeds_entry_id_seq'::regclass)")
        [(value,)] = cursor.fetchall()
    finally:
        cursor.close()
    return value
