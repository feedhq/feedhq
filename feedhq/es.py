from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy

from django.db import connection
from django.conf import settings
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk as es_bulk, BulkIndexError


client = Elasticsearch(settings.ES_NODES,
                       sniff_on_start=False,
                       sniff_on_connection_fail=True)


def user_alias(user_id):
    assert isinstance(user_id, int), repr(user_id)
    return settings.ES_ALIAS_TEMPLATE.format(user_id)


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
    aggs = {}
    for pk in feed_ids:
        term = {'term': {'feed': pk}}
        if only_unread:
            term = {'and': [
                {'term': {'read': False}},
                term,
            ]}
        aggs[pk] = {
            'global': True,
            'filter': term,
        }
    query = {
        'aggs': aggs,
    }
    return client.search(index=user_alias(user.pk),
                         doc_type='entries',
                         body=query,
                         params={'size': 0}).get('aggregations', {})


def entry(user, id, annotate_results=True):
    from .feeds.models import EsEntry
    result = client.get(user_alias(user.pk), id)
    entry = EsEntry(result)
    if annotate_results:
        entry.user = user
        entry.feed = user.feeds.select_related('category').get(pk=entry.feed)
        if getattr(entry, 'category', None):
            entry.category = entry.feed.category
    return entry


def mget(user, pks, annotate_results=True):
    from .feeds.models import EsEntry
    docs = client.mget({'ids': pks}, index=user_alias(user.pk),
                       doc_type='entries')['docs']
    results = []
    for doc in docs:
        if not doc['found']:
            continue
        if doc['_source']['user'] != user.pk:
            # XXX elasticsearch doesn't seem to do an mget within an alias
            # scope but rather in the global context.
            # See url-access-control in the ES docs. Requires a server setting,
            # safer to enforce here.
            continue
        doc['_id'] = int(doc['_id'])
        results.append(EsEntry(doc))
    if annotate_results:
        results = _annotate(results, user)
    return results


def _annotate(results, user):
    feed_ids = set([e.feed for e in results])
    if not feed_ids:
        return results
    feeds = user.feeds.filter(pk__in=feed_ids).select_related('category')
    by_pk = {feed.pk: feed for feed in feeds}

    annotated = []
    for entry in results:
        try:
            feed = by_pk[entry.feed]
        except KeyError:
            # FIXME feed deleted -- delete entries for this feed ID
            continue
        if getattr(entry, 'category', None):
            entry.category = feed.category
        entry.feed = feed
        entry.user = user
        annotated.append(entry)
    return annotated


def next_id():
    cursor = connection.cursor()
    try:
        cursor.execute("select nextval('feeds_entry_id_seq'::regclass)")
        [(value,)] = cursor.fetchall()
    finally:
        cursor.close()
    return value


def _and_or_term(values):
    if len(values) == 1:
        return values[0]
    return {'and': values}


def _lookup(name, values):
    _range = {}
    _or = None
    for lk in values.values():
        for key, value in lk.items():
            if key in ['lte', 'gte', 'lt', 'gt']:
                _range[key] = value
            elif key == 'in':
                if len(value) == 1:
                    _or = {'term': {name: value[0]}}
                else:
                    _or = {'or': [{'term': {name: val}} for val in value]}
    if _range and _or:
        raise ValueError("Will not combine range and __in lookups.")
    if _range:
        return {'range': {name: _range}}
    elif _or:
        return _or
    raise ValueError("Empty lookup")


class EntryQuery(object):
    def __init__(self, **kwargs):
        self.indices = ''
        self.filters = {}
        self.aggs = {}
        self.terms_aggs = {}
        self.query_agg = False
        self.query_aggs = {}
        self.query = None
        self.source = {}
        self.ordering = ['timestamp:desc', 'id:desc']
        self.filter(clone=False, **kwargs)

    def _clone(self):
        q = self.__class__()
        q.indices = self.indices
        q.filters = deepcopy(self.filters)
        q.aggs = deepcopy(self.aggs)
        q.terms_aggs = deepcopy(self.terms_aggs)
        q.query_agg = self.query_agg
        q.query_aggs = deepcopy(self.query_aggs)
        q.query = self.query
        q.source = deepcopy(self.source)
        q.ordering = self.ordering
        return q

    def filter(self, clone=True, or_=False, **kwargs):
        q = self._clone() if clone else self
        q._apply_filters(or_=or_, **kwargs)
        return q

    def exclude(self, **kwargs):
        q = self._clone()
        q._apply_filters(negate=True, **kwargs)
        return q

    def _apply_filters(self, negate=False, or_=False, **kwargs):
        lookups = defaultdict(dict)
        filters = {}
        for key, value in kwargs.items():
            if '__' in key:
                field, lookup = key.split('__')
                lookups[field][lookup] = value
                continue

            if key == 'user':
                if negate:
                    raise ValueError("Can't exclude an index.")
                self.indices = user_alias(value)
                continue

            if key == 'query':
                if negate:
                    value = 'NOT {0}'.format(value)
                self.query = value
                continue

            term = {'term': {key: value}}
            if negate:
                term = {'not': term}

            filters[key] = term

        for key, lookup in lookups.items():
            filter_ = _lookup(key, lookups)
            if negate:
                filter_ = {'not': filter_}
            filters[key] = filter_

        if filters:
            if or_:
                if 'or' not in self.filters:
                    self.filters['or'] = {'or': []}
                self.filters['or']['or'].extend(filters.values())
            else:
                self.filters.update(filters)

    def defer(self, *fields):
        q = self._clone()
        q.source['exclude'] = fields
        return q

    def only(self, *fields):
        q = self._clone()
        q.source['include'] = fields
        return q

    def aggregate(self, name, **kwargs):
        """
        Add an aggregation to the current query.

        kwargs filter the aggregation.

        To generate an aggregation based on the current query, just
        pass '__query__' as aggregation name.
        """
        q = self._clone()

        if name == '__query__':
            q.query_agg = True
            return q

        filters = {}
        lookups = defaultdict(dict)
        for key, value in kwargs.items():
            if '__' in key:
                field, lookup = key.split('__')
                lookups[field][lookup] = value
                continue

            filters[key] = {'term': {key: value}}

        for key, lookup in lookups.items():
            filters[key] = _lookup(key, lookup)

        if filters:
            q.aggs[name] = {'filter': _and_or_term(list(filters.values()))}
        else:
            q.terms_aggs[name] = {'terms': {'field': name, 'size': 0}}
        return q

    def query_aggregate(self, name, **kwargs):
        q = self._clone()
        filters = []
        for key, value in kwargs.items():
            filters.append({'term': {key: value}})
        if filters:
            q.query_aggs[name] = {'filter': _and_or_term(filters)}
        else:
            q.query_aggs[name] = {'filter': {'match_all': {}}}
        return q

    def order_by(self, *criteria):
        if not criteria:
            raise ValueError("Must provide fields to sort on")
        q = self._clone()
        q.ordering = []
        for crit in criteria:
            order = 'asc'
            if crit.startswith('-'):
                order = 'desc'
                crit = crit[1:]
            q.ordering.append('{0}:{1}'.format(crit, order))
        return q

    def fetch(self, page=1, per_page=50, annotate=None):
        from .feeds.models import EsEntry
        filters = {}
        if self.filters:
            filters['filter'] = _and_or_term(list(self.filters.values()))
        else:
            filters['filter'] = {'match_all': {}}

        if self.terms_aggs or self.query_agg:
            self.aggs['query'] = {'filter': filters['filter']}
            if self.terms_aggs:
                self.aggs['query']['aggs'] = self.terms_aggs

        if self.query_aggs:
            self.aggs.update(self.query_aggs)

        if self.query:
            filters['query'] = query = {'query_string': {'query': self.query}}

        query = {}

        if filters:
            query['query'] = {'filtered': filters}

        if self.source:
            query['_source'] = self.source

        if self.aggs:
            query['aggs'] = {
                'entries': {
                    'global': {},
                    'aggs': self.aggs
                },
            }

        results = client.search(
            index=self.indices,
            doc_type='entries',
            body=query,
            params={
                'from': (page - 1) * per_page,
                'sort': ",".join(self.ordering),
                'size': per_page,
            },
        )
        results['hits'] = [EsEntry(hit) for hit in results['hits']['hits']]
        if annotate is not None:
            results['hits'] = _annotate(results['hits'], annotate)
        return results


class EntryManager(object):
    def user(self, user_or_id):
        if not isinstance(user_or_id, int):
            user_or_id = user_or_id.pk
        return EntryQuery(user=user_or_id)
manager = EntryManager()


@contextmanager
def ignore_bulk_error(*statuses):
    try:
        yield
    except BulkIndexError as e:
        for doc in e.args[1]:
            if doc['update']['status'] not in statuses:
                raise
