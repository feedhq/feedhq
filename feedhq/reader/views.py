import json
import logging
import re
import struct
import urlparse

from datetime import timedelta
from urllib import urlencode

import opml

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import Sum, Q
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from lxml.etree import XMLSyntaxError

from rest_framework import exceptions
from rest_framework.authentication import SessionAuthentication
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.parsers import XMLParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from ..feeds.forms import FeedForm, user_lock
from ..feeds.models import Feed, UniqueFeed, Category
from ..feeds.utils import epoch_to_utc
from ..feeds.views import save_outline
from ..profiles.models import User
from ..utils import is_email
from .authentication import GoogleLoginAuthentication
from .exceptions import PermissionDenied, BadToken
from .models import generate_auth_token, generate_post_token, check_post_token
from .renderers import (PlainRenderer, GoogleReaderXMLRenderer, AtomRenderer,
                        AtomHifiRenderer)


logger = logging.getLogger(__name__)

MISSING_SLASH_RE = re.compile("^(https?:\/)[^\/]")


def item_id(value):
    """
    Converts an input to a proper (integer) item ID.
    """
    if value.startswith('tag:google.com'):
        try:
            value = int(value.split('/')[-1], 16)
            value = struct.unpack("l", struct.pack("L", value))[0]
        except (ValueError, IndexError):
            raise exceptions.ParseError(
                "Unrecognized item. Must be of the form "
                "'tag:google.com,2005:reader/item/<item_id>'")
    elif value.isdigit():
        value = int(value)
    else:
        raise exceptions.ParseError(
            "Unrecognized item. Must be of the form "
            "'tag:google.com,2005:reader/item/<item_id>'")
    return value


def tag_value(tag):
    try:
        return tag.rsplit('/', 1)[1]
    except IndexError:
        raise exceptions.ParseError(
            "Bad tag format. Must be of the form "
            "'user/-/state/com.google/<tag>'. Allowed tags: 'read', "
            "'kept-unread', 'starred', 'broadcast'.")


def is_stream(value, user_id):
    stream_prefix = "user/-/state/com.google/"
    stream_user_prefix = "user/{0}/state/com.google/".format(user_id)
    if value.startswith((stream_prefix, stream_user_prefix)):
        if value.startswith(stream_prefix):
            prefix = stream_prefix
        else:
            prefix = stream_user_prefix
        return value[len(prefix):]
    return False


def is_label(value, user_id):
    label_prefix = "user/-/label/"
    label_user_prefix = "user/{0}/label/".format(user_id)
    if value.startswith((label_prefix, label_user_prefix)):
        if value.startswith(label_prefix):
            prefix = label_prefix
        else:
            prefix = label_user_prefix
        return value[len(prefix):]
    return False


def feed_url(stream):
    url = stream[len('feed/'):]
    missing_slash = MISSING_SLASH_RE.match(url)
    if missing_slash:
        start = missing_slash.group(1)
        url = u'{0}/{1}'.format(start, url[len(start):])
    return url


class ForceNegotiation(DefaultContentNegotiation):
    """
    Forces output even if ?output= is wrong when we have
    only one renderer.
    """
    def __init__(self, force_format=None):
        self.force_format = force_format
        super(ForceNegotiation, self).__init__()

    def select_renderer(self, request, renderers, format_suffix=None):
        if self.force_format is not None:
            format_suffix = self.force_format
        return super(ForceNegotiation, self).select_renderer(
            request, renderers, format_suffix)

    def filter_renderers(self, renderers, format):
        if len(renderers) == 1:
            return renderers
        renderers = [r for r in renderers if r.format == format]
        if not renderers:
            raise Http404
        return renderers


class Login(APIView):
    http_method_names = ['get', 'post']
    renderer_classes = [PlainRenderer]

    def handle_exception(self, exc):
        if isinstance(exc, PermissionDenied):
            return Response(exc.detail, status=exc.status_code)
        return super(Login, self).handle_exception(exc)

    def initial(self, request, *args, **kwargs):
        if request.method == 'POST':
            querydict = request.DATA
        elif request.method == 'GET':
            querydict = request.GET
        if not 'Email' in querydict or not 'Passwd' in querydict:
            raise PermissionDenied()
        self.querydict = querydict

    def post(self, request, *args, **kwargs):
        if is_email(self.querydict['Email']):
            clause = Q(email__iexact=self.querydict['Email'])
        else:
            clause = Q(username__iexact=self.querydict['Email'])
        clause = clause & Q(is_active=True)
        try:
            user = User.objects.get(clause)
        except User.DoesNotExist:
            raise PermissionDenied()
        if not user.check_password(self.querydict['Passwd']):
            raise PermissionDenied()
        client = request.GET.get('client', request.DATA.get('client', ''))
        token = generate_auth_token(
            user,
            client=client,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
        return Response("SID={t}\nLSID={t}\nAuth={t}".format(t=token))
    get = post
login = Login.as_view()


class ReaderView(APIView):
    authentication_classes = [SessionAuthentication,
                              GoogleLoginAuthentication]
    renderer_classes = [JSONRenderer, GoogleReaderXMLRenderer]
    content_negotiation_class = ForceNegotiation
    require_post_token = True

    def initial(self, request, *args, **kwargs):
        super(ReaderView, self).initial(request, *args, **kwargs)
        if request.method == 'POST' and self.require_post_token:
            token = request.DATA.get('T', request.GET.get('T', None))
            if token is None:
                logger.info(
                    u"Missing POST token, {0}".format(request.DATA.dict())
                )
                raise exceptions.ParseError("Missing 'T' POST token")
            user_id = check_post_token(token)
            if not user_id == request.user.pk:
                raise BadToken

    def handle_exception(self, exc):
        if isinstance(exc, BadToken):
            self.headers['X-Reader-Google-Bad-Token'] = "true"
        return super(ReaderView, self).handle_exception(exc)

    def label(self, value):
        if not is_label(value, self.request.user.pk):
            raise exceptions.ParseError("Unknown label: {0}".format(value))
        return value.split('/')[-1]

    def get_content_negotiator(self):
        if not getattr(self, '_negotiator', None):
            force_format = self.kwargs.get('output')
            self._negotiator = self.content_negotiation_class(force_format)
        return self._negotiator


class TokenView(ReaderView):
    http_method_names = ['get', 'post']
    renderer_classes = [PlainRenderer]
    require_post_token = False

    def get(self, request, *args, **kwargs):
        token = generate_post_token(request.user)
        return Response(token)
    post = get
token = TokenView.as_view()


class UserInfo(ReaderView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        return Response({
            "userName": request.user.username,
            "userEmail": request.user.email,
            "userId": str(request.user.pk),
            "userProfileId": str(request.user.pk),
            "isBloggerUser": False,
            "signupTimeSec": int(request.user.date_joined.strftime("%s")),
            "isMultiLoginEnabled": False,
        })
user_info = UserInfo.as_view()


class StreamPreference(ReaderView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        return Response({"streamprefs": {}})
stream_preference = StreamPreference.as_view()


class PreferenceList(ReaderView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        return Response({"prefs": [{
            "id": "lhn-prefs",
            "value": json.dumps({"subscriptions": {"ssa": "true"}},
                                separators=(',', ':')),
        }]})
preference_list = PreferenceList.as_view()


class UnreadCount(ReaderView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        feeds = request.user.feeds.filter(unread_count__gt=0)
        last_updates = request.user.last_updates()
        unread_counts = []
        forced = False
        for feed in feeds:
            if feed.url not in last_updates and not forced:
                last_updates = request.user.refresh_updates()
                forced = True
            feed_data = {
                "id": u"feed/{0}".format(feed.url),
                "count": feed.unread_count,
            }
            ts = last_updates[feed.url]
            if ts:
                feed_data['newestItemTimestampUsec'] = '{0}000000'.format(ts)
            unread_counts.append(feed_data)

        # We can't annotate with Max('feeds__entries__date') when fetching the
        # categories since it creates duplicates and returns wrong counts.
        cat_ts = {}
        for feed in feeds:
            if feed.category_id in cat_ts and last_updates[feed.url]:
                cat_ts[feed.category_id] = max(cat_ts[feed.category_id],
                                               last_updates[feed.url])
            elif last_updates[feed.url]:
                cat_ts[feed.category_id] = last_updates[feed.url]
        categories = request.user.categories.annotate(
            unread_count=Sum('feeds__unread_count'),
        ).filter(unread_count__gt=0)
        for cat in categories:
            info = {
                "id": label_key(request, cat),
                "count": cat.unread_count,
            }
            if cat.pk in cat_ts:
                info["newestItemTimestampUsec"] = '{0}000000'.format(
                    cat_ts[cat.pk])
            unread_counts.append(info)

        # Special items:
        # reading-list is the global counter
        if cat_ts.values():
            unread_counts += [{
                "id": "user/{0}/state/com.google/reading-list".format(
                    request.user.pk),
                "count": sum([f.unread_count for f in feeds]),
                "newestItemTimestampUsec": '{0}000000'.format(max(
                    cat_ts.values())),
            }]
        return Response({
            "max": 1000,
            "unreadcounts": unread_counts,
        })
unread_count = UnreadCount.as_view()


class DisableTag(ReaderView):
    http_method_names = ['post']
    renderer_classes = [PlainRenderer]

    def post(self, request, *args, **kwargs):
        if not 's' in request.DATA and not 't' in request.DATA:
            raise exceptions.ParseError("Missing required 's' parameter")

        if 's' in request.DATA:
            name = is_label(request.DATA['s'], request.user.pk)
        else:
            name = request.DATA['t']

        try:
            category = request.user.categories.get(name=name)
        except Category.DoesNotExist:
            raise exceptions.ParseError(
                "Tag '{0}' does not exist".format(name))

        category.feeds.update(category=None)
        category.delete()
        return Response("OK")
disable_tag = DisableTag.as_view()


class RenameTag(ReaderView):
    http_method_names = ['post']
    renderer_classes = [PlainRenderer]

    def post(self, request, *args, **kwargs):
        if not 's' in request.DATA and not 't' in request.DATA:
            raise exceptions.ParseError("Missing required 's' parameter")

        if not 'dest' in request.DATA:
            raise exceptions.ParseError("Missing required 'dest' parameter")

        new_name = is_label(request.DATA['dest'], request.user.pk)
        if not new_name:
            raise exceptions.ParseError("Invalid 'dest' parameter")

        if 's' in request.DATA:
            name = is_label(request.DATA['s'], request.user.pk)
        else:
            name = request.DATA['t']

        try:
            category = request.user.categories.get(name=name)
        except Category.DoesNotExist:
            raise exceptions.ParseError(
                "Tag '{0}' does not exist".format(name))

        category.name = new_name
        category.save()

        return Response("OK")
rename_tag = RenameTag.as_view()


class TagList(ReaderView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        tags = [{
            "id": "user/{0}/state/com.google/starred".format(request.user.pk),
            "sortid": "A0000001",
        }, {
            "id": "user/{0}/states/com.google/broadcast".format(
                request.user.pk),
            "sortid": "A0000002",
        }]
        index = 3
        for cat in request.user.categories.order_by('name'):
            tags.append({
                "id": label_key(request, cat),
                "sortid": "A{0}".format(str(index).zfill(7)),
            })
            index += 1
        return Response({'tags': tags})
tag_list = TagList.as_view()


class SubscriptionList(ReaderView):
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        feeds = request.user.feeds.select_related('category',).order_by(
            'category__name', 'name')
        uniques = UniqueFeed.objects.filter(url__in=[f.url for f in feeds])
        unique_map = {}
        for unique in uniques:
            if unique.link:
                unique_map[unique.url] = unique.link

        subscriptions = []
        for index, feed in enumerate(feeds):
            subscription = {
                "id": u"feed/{0}".format(feed.url),
                "title": feed.name,
                "categories": [],
                "sortid": "B{0}".format(str(index).zfill(7)),
                "htmlUrl": unique_map.get(feed.url, feed.url),
                "firstitemmsec": (timezone.now() - timedelta(
                    days=request.user.ttl or 365)).strftime("%s000"),
            }
            if feed.category is not None:
                subscription['categories'].append({
                    "id": label_key(request, feed.category),
                    "label": feed.category.name,
                })
            subscriptions.append(subscription)
        return Response({
            "subscriptions": subscriptions
        })
subscription_list = SubscriptionList.as_view()


class EditSubscription(ReaderView):
    http_method_names = ['post']
    renderer_classes = [PlainRenderer]

    def post(self, request, *args, **kwargs):
        action = request.DATA.get('ac')
        if action is None:
            raise exceptions.ParseError("Missing 'ac' parameter")

        if not 's' in request.DATA:
            raise exceptions.ParseError("Missing 's' parameter")

        if not request.DATA['s'].startswith('feed/'):
            raise exceptions.ParseError(
                u"Unrecognized stream: {0}".format(request.DATA['s']))
        url = feed_url(request.DATA['s'])

        if action == 'subscribe':
            form = FeedForm(data={'url': url}, user=request.user)
            if not form.is_valid():
                errors = dict(form._errors)
                if 'url' in errors:
                    raise exceptions.ParseError(errors['url'][0])

            if 'a' in request.DATA:
                name = self.label(request.DATA['a'])
                category, created = request.user.categories.get_or_create(
                    name=name)
            else:
                category = None

            request.user.feeds.create(
                url=url,
                name=request.DATA.get('t', form.cleaned_data['title']),
                category=category)

        elif action == 'unsubscribe':
            request.user.feeds.filter(url=url).delete()
        elif action == 'edit':
            qs = request.user.feeds.filter(url=url)
            query = {}
            if 'r' in request.DATA:
                name = self.label(request.DATA['r'])
                qs = qs.filter(category__name=name)
                query['category'] = None
            if 'a' in request.DATA:
                name = self.label(request.DATA['a'])
                category, created = request.user.categories.get_or_create(
                    name=name)
                query['category'] = category
            if 't' in request.DATA:
                query['name'] = request.DATA['t']
            if query:
                qs.update(**query)
        else:
            msg = u"Unrecognized action: {0}".format(action)
            logger.info(msg)
            raise exceptions.ParseError(msg)
        return Response("OK")
edit_subscription = EditSubscription.as_view()


class QuickAddSubscription(ReaderView):
    http_method_names = ['post']

    def post(self, request, *args, **kwargs):
        if not 'quickadd' in request.DATA:
            raise exceptions.ParseError("Missing 'quickadd' parameter")

        url = request.DATA['quickadd']
        if url.startswith('feed/'):
            url = feed_url(url)

        form = FeedForm(data={'url': url}, user=request.user)
        if not form.is_valid():
            errors = dict(form._errors)
            if 'url' in errors:
                raise exceptions.ParseError(errors['url'][0])

        name = form.cleaned_data['title']
        if not name:
            name = urlparse.urlparse(url).netloc
        request.user.feeds.create(name=name, url=url)
        return Response({
            "numResults": 1,
            "query": url,
            "streamId": u"feed/{0}".format(url),
        })
quickadd_subscription = QuickAddSubscription.as_view()


class Subscribed(ReaderView):
    http_method_names = ['get']
    renderer_classes = [PlainRenderer]

    def get(self, request, *args, **kwargs):
        if not 's' in request.GET:
            raise exceptions.ParseError("Missing 's' parameter")
        feed = request.GET['s']
        if not feed.startswith('feed/'):
            raise exceptions.ParseError(
                "Unrecognized feed format. Use 'feed/<url>'")
        url = feed_url(feed)
        return Response(str(
            request.user.feeds.filter(url=url).exists()
        ).lower())
subscribed = Subscribed.as_view()


def get_q(stream, user_id, exception=False):
    """Given a stream ID, returns a Q object for this stream."""
    stream_q = None
    if stream.startswith("feed/"):
        url = feed_url(stream)
        stream_q = Q(feed__url=url)
    elif is_stream(stream, user_id):
        state = is_stream(stream, user_id)
        if state == 'read':
            stream_q = Q(read=True)
        elif state == 'kept-unread':
            stream_q = Q(read=False)
        elif state in ['broadcast', 'broadcast-friends']:
            stream_q = Q(broadcast=True)
        elif state == 'reading-list':
            stream_q = Q()
        elif state == 'starred':
            stream_q = Q(starred=True)
    elif is_label(stream, user_id):
        name = is_label(stream, user_id)
        stream_q = Q(feed__category__name=name)
    else:
        msg = u"Unrecognized stream: {0}".format(stream)
        logger.info(msg)
        if exception:
            raise exceptions.ParseError(msg)
    return stream_q


def get_stream_q(streams, user_id, exclude=None, include=None, limit=None,
                 offset=None):
    """
    Returns a Q object that can be used to filter a queryset of entries.

    streams: list of streams to include
    exclude: stream to exclude
    limit: unix timestamp from which to consider entries
    offset: unix timestamp to which to consider entries
    """
    q = None
    if streams.startswith('splice/'):
        streams = streams[len('splice/'):].split('|')
    else:
        streams = [streams]

    for stream in streams:
        stream_q = get_q(stream, user_id, exception=True)
        if stream_q is not None:
            if q is None:
                q = stream_q
            else:
                q |= stream_q

    # ?it=user/stuff or feed/stuff to only include something from the query
    if include is not None:
        for inc in include:
            include_q = get_q(inc, user_id)
            if include_q is not None and q is not None:
                q &= include_q

    # ?xt=user/stuff or feed/stuff to exclude something from the query
    if exclude is not None:
        for ex in exclude:
            exclude_q = get_q(ex, user_id)
            if exclude_q is not None and q is not None:
                q &= ~exclude_q

    # ?ot=<timestamp> for limiting in time
    if limit is not None:
        try:
            timestamp = int(limit)
        except ValueError:
            raise exceptions.ParseError(
                "Malformed 'ot' parameter. Must be a unix timstamp")
        else:
            limit = epoch_to_utc(timestamp)
            if q is not None:
                q &= Q(date__gte=limit)
    # ?nt=<timestamp>
    if offset is not None:
        try:
            timestamp = int(offset)
        except ValueError:
            raise exceptions.ParseError(
                "Malformed 'nt' parameter. Must be a unix timstamp")
        else:
            offset = epoch_to_utc(timestamp)
            if q is not None:
                q &= Q(date__lte=offset)
    if q is None:
        return Q(pk__lte=0)
    return q


def pagination(entries, n=None, c=None):
    # ?n=20 (default), ?c=<continuation> for offset
    if n is None:
        n = 20
    if c is None:
        c = 'page1'
    try:
        pagination_by = int(n)
    except ValueError:
        raise exceptions.ParseError("'n' must be an integer")
    try:
        page = int(c[4:])
    except ValueError:
        raise exceptions.ParseError("Invalid 'c' continuation string")

    continuation = None
    if page * pagination_by < entries.count():
        continuation = 'page{0}'.format(page + 1)

    start = max(0, (page - 1) * pagination_by)
    end = page * pagination_by
    return start, end, continuation


def label_key(request, label):
    return u"user/{0}/label/{1}".format(request.user.pk, label.name)


def serialize_entry(request, entry, uniques):
    reading_list = "user/{0}/state/com.google/reading-list".format(
        request.user.pk)
    read = "user/{0}/state/com.google/read".format(request.user.pk)
    starred = "user/{0}/state/com.google/starred".format(request.user.pk)
    broadcast = "user/{0}/state/com.google/broadcast".format(request.user.pk)

    item = {
        "crawlTimeMsec": entry.date.strftime("%s000"),
        "timestampUsec": entry.date.strftime("%s000000"),
        "id": "tag:google.com,2005:reader/item/{0}".format(entry.hex_pk),
        "categories": [reading_list],
        "title": entry.title,
        "published": int(entry.date.strftime("%s")),
        "updated": int(entry.date.strftime("%s")),
        "alternate": [{
            "href": entry.link,
            "type": "text/html",
        }],
        "content": {
            "direction": "ltr",
            "content": entry.subtitle,
        },
        "origin": {
            "streamId": u"feed/{0}".format(entry.feed.url),
            "title": entry.feed.name,
            "htmlUrl": uniques.get(entry.feed.url, entry.feed.url),
        },
    }
    if entry.feed.category is not None:
        item['categories'].append(
            label_key(request, entry.feed.category))
    if entry.read:
        item['categories'].append(read)
    if entry.starred:
        item['categories'].append(starred)
    if entry.broadcast:
        item['categories'].append(broadcast)
    if entry.author:
        item['author'] = entry.author
    return item


def get_unique_map(user, force=False):
    cache_key = 'reader:unique_map:{0}'.format(user.pk)
    value = cache.get(cache_key)
    if value is None or force:
        unique = UniqueFeed.objects.raw(
            "select id, url, muted from feeds_uniquefeed u "
            "where exists ("
            "select 1 from feeds_feed f "
            "left join auth_user s "
            "on f.user_id = s.id "
            "where f.url = u.url and f.user_id = %s)", [user.pk])
        value = {}
        for u in unique:
            value[u.url] = u.link
        cache.set(cache_key, value, 60)
    return value


class StreamContents(ReaderView):
    http_method_names = ['get']
    renderer_classes = ReaderView.renderer_classes + [AtomRenderer,
                                                      AtomHifiRenderer]

    def get(self, request, *args, **kwargs):
        content_id = kwargs['content_id']
        if content_id is None:
            content_id = 'user/-/state/com.google/reading-list'
        base = {
            "direction": "ltr",
            "id": content_id,
            "self": [{
                "href": request.build_absolute_uri(request.path),
            }],
            "author": request.user.username,
            "updated": int(timezone.now().strftime("%s")),
            "items": [],
        }

        if content_id.startswith("feed/"):
            url = feed_url(content_id)
            feeds = request.user.feeds.filter(url=url).order_by('pk')[:1]
            if len(feeds) == 0:
                raise Http404
            feed = feeds[0]
            base.update({
                'title': feed.name,
                'description': feed.name,
            })
            try:
                unique = UniqueFeed.objects.get(url=url)
                uniques = {url: unique.link}
            except UniqueFeed.DoesNotExist:
                uniques = {url: url}
                base.update({
                    'alternate': [{
                        'href': url,
                        'type': 'text/html',
                    }],
                })
            else:
                base.update({
                    'alternate': [{
                        'href': unique.link,
                        'type': 'text/html',
                    }],
                })
                updated = unique.last_update
                if updated is None:
                    updated = timezone.now() - timedelta(days=7)
                base['updated'] = int(updated.strftime('%s'))

        elif is_stream(content_id, request.user.pk):
            uniques = get_unique_map(request.user)

            state = is_stream(content_id, request.user.pk)
            base['id'] = 'user/{0}/state/com.google/{1}'.format(
                request.user.pk, state)
            if state == 'reading-list':
                base['title'] = u"{0}'s reading list on FeedHQ".format(
                    request.user.username)

            elif state == 'kept-unread':
                base['title'] = u"{0}'s unread items on FeedHQ".format(
                    request.user.username)

            elif state == 'starred':
                base["title"] = "Starred items on FeedHQ"

            elif state in ['broadcast', 'broadcast-friends']:
                base["title"] = "Broadcast items on FeedHQ"

        elif is_label(content_id, request.user.pk):
            name = is_label(content_id, request.user.pk)
            base['title'] = u'"{0}" via {1} on FeedHQ'.format(
                name, request.user.username)
            base['id'] = u'user/{0}/label/{1}'.format(request.user.pk, name)
            uniques = get_unique_map(request.user)
        else:
            msg = u"Unknown stream id: {0}".format(content_id)
            logger.info(msg)
            raise exceptions.ParseError(msg)

        entries = request.user.entries.filter(
            get_stream_q(content_id, request.user.pk,
                         exclude=request.GET.getlist('xt'),
                         include=request.GET.getlist('it'),
                         limit=request.GET.get('ot'),
                         offset=request.GET.get('nt')),
        ).select_related('feed', 'feed__category')

        # Ordering
        # ?r=d|n last entry first (default), ?r=o oldest entry first
        ordering = 'date' if request.GET.get('r', 'd') == 'o' else '-date'

        start, end, continuation = pagination(entries, n=request.GET.get('n'),
                                              c=request.GET.get('c'))

        qs = {}
        if start > 0:
            qs['c'] = request.GET['c']

        if 'output' in request.GET:
            qs['output'] = request.GET['output']

        if qs:
            base['self'][0]['href'] += '?{0}'.format(urlencode(qs))

        if continuation:
            base['continuation'] = continuation

        forced = False  # Make at most 1 full refetch
        for entry in entries.order_by(ordering)[start:end]:
            if entry.feed.url not in uniques and not forced:
                uniques = get_unique_map(request.user, force=True)
                forced = True
            item = serialize_entry(request, entry, uniques)
            base['items'].append(item)
        return Response(base)
stream_contents = StreamContents.as_view()


class StreamItemsIds(ReaderView):
    http_method_names = ['get', 'post']
    require_post_token = False

    def get(self, request, *args, **kwargs):
        if not 'n' in request.GET:
            raise exceptions.ParseError("Required 'n' parameter")
        if not 's' in request.GET:
            raise exceptions.ParseError("Required 's' parameter")
        entries = request.user.entries.filter(
            get_stream_q(
                request.GET['s'], request.user.pk,
                exclude=request.GET.getlist('xt'),
                include=request.GET.getlist('it'),
                limit=request.GET.get('ot'),
                offset=request.GET.get('nt'))).order_by('date')

        start, end, continuation = pagination(entries, n=request.GET.get('n'),
                                              c=request.GET.get('c'))

        data = {}
        if continuation:
            data['continuation'] = continuation

        if request.GET.get("includeAllDirectStreamIds") == 'true':
            entries = entries.select_related('feed').values('pk', 'date',
                                                            'feed__url')
            item_refs = [{
                'id': str(e['pk']),
                'directStreamIds': [
                    u'feed/{0}'.format(e['feed__url']),
                ],
                'timestampUsec': e['date'].strftime("%s000000"),
            } for e in entries[start:end]]
        else:
            entries = entries.values('pk', 'date')
            item_refs = [{
                'id': str(e['pk']),
                'directStreamIds': [],
                'timestampUsec': e['date'].strftime("%s000000"),
            } for e in entries[start:end]]
        data['itemRefs'] = item_refs
        return Response(data)
    post = get
stream_items_ids = StreamItemsIds.as_view()


class StreamItemsCount(ReaderView):
    renderer_classes = [PlainRenderer]

    def get(self, request, *args, **kwargs):
        if not 's' in request.GET:
            raise exceptions.ParseError("Missing 's' parameter")
        entries = request.user.entries.filter(get_stream_q(request.GET['s'],
                                                           request.user.pk))
        data = str(entries.count())
        if request.GET.get('a') == 'true':
            data = '{0}#{1}'.format(
                data, entries.order_by('-date')[0].date.strftime("%B %d, %Y"))
        return Response(data)
stream_items_count = StreamItemsCount.as_view()


class StreamItemsContents(ReaderView):
    http_method_names = ['get', 'post']
    renderer_classes = ReaderView.renderer_classes + [AtomRenderer,
                                                      AtomHifiRenderer]
    require_post_token = False

    def get(self, request, *args, **kwargs):
        items = request.GET.getlist('i', request.DATA.getlist('i'))
        if len(items) == 0:
            raise exceptions.ParseError(
                "Required 'i' parameter: items IDs to send back")

        ids = map(item_id, items)

        entries = request.user.entries.filter(pk__in=ids).select_related(
            'feed', 'feed__category')

        if not entries:
            raise exceptions.ParseError("No items found")

        uniques = get_unique_map(request.user)
        items = []
        for e in entries:
            if e.feed.url not in uniques:
                uniques = get_unique_map(request.user, force=True)
            items.append(serialize_entry(request, e, uniques))

        base = {
            'direction': 'ltr',
            'id': u'feed/{0}'.format(entries[0].feed.url),
            'title': entries[0].feed.name,
            'self': [{
                'href': request.build_absolute_uri(),
            }],
            'alternate': [{
                'href': uniques.get(entries[0].feed.url, entries[0].feed.url),
                'type': 'text/html',
            }],
            'updated': int(timezone.now().strftime("%s")),
            'items': items,
            'author': request.user.username,
        }
        return Response(base)
    post = get
stream_items_contents = StreamItemsContents.as_view()


class EditTag(ReaderView):
    http_method_names = ['post']
    renderer_classes = [PlainRenderer]

    def post(self, request, *args, **kwargs):
        if not 'i' in request.DATA:
            raise exceptions.ParseError(
                "Missing 'i' in request data. "
                "'tag:gogle.com,2005:reader/item/<item_id>'")
        entry_ids = map(item_id, request.DATA.getlist('i'))
        add = 'a' in request.DATA
        remove = 'r' in request.DATA
        if not add and not remove:
            raise exceptions.ParseError(
                "Specify a tag to add or remove. Add: 'a' parameter, "
                "remove: 'r' parameter.")

        to_add = []
        if add:
            to_add = map(tag_value, request.DATA.getlist('a'))

        to_remove = []
        if remove:
            to_remove = map(tag_value, request.DATA.getlist('r'))

        query = {}
        for tag in to_add:
            if tag == 'kept-unread':
                query['read'] = False

            elif tag in ['starred', 'broadcast', 'read']:
                query[tag] = True

            elif tag.startswith('tracking-'):
                # There is no tracking. Carry on :)
                # More context: http://googlesystem.blogspot.ch/2008/03/explore-your-interactions-with-google.html  # noqa
                # FeedHQ doesn't have that historical data.
                continue

            else:
                logger.info(u"Unhandled tag {0}".format(tag))
                raise exceptions.ParseError(
                    "Unrecognized tag: {0}".format(tag))

        for tag in to_remove:
            if tag == 'kept-unread':
                query['read'] = True

            elif tag in ['starred', 'broadcast', 'read']:
                query[tag] = False

            elif tag.startswith('tracking-'):
                # There is no tracking. Carry on :)
                continue

            else:
                logger.info(u"Unhandled tag {0}".format(tag))
                raise exceptions.ParseError(
                    "Unrecognized tag: {0}".format(tag))

        request.user.entries.filter(pk__in=entry_ids).update(**query)
        merged = to_add + to_remove
        if 'read' in merged or 'kept-unread' in merged:
            feeds = Feed.objects.filter(
                pk__in=request.user.entries.filter(
                    pk__in=entry_ids).values_list('feed_id', flat=True))
            for feed in feeds:
                feed.update_unread_count()
        return Response("OK")
edit_tag = EditTag.as_view()


class MarkAllAsRead(ReaderView):
    http_method_names = ['post']
    renderer_classes = [PlainRenderer]

    def post(self, request, *args, **kwargs):
        if not 's' in request.DATA:
            raise exceptions.ParseError("Missing 's' parameter")
        entries = request.user.entries
        limit = None
        if 'ts' in request.DATA:
            try:
                timestamp = int(request.DATA['ts'])
            except ValueError:
                raise exceptions.ParseError(
                    "Invalid 'ts' parameter. Must be a number of microseconds "
                    "since epoch.")
            limit = epoch_to_utc(timestamp / 1000000)  # microseconds -> secs
            entries = entries.filter(date__lte=limit)

        stream = request.DATA['s']

        if stream.startswith('feed/'):
            url = feed_url(stream)
            entries = entries.filter(feed__url=url)
        elif is_label(stream, request.user.pk):
            name = is_label(stream, request.user.pk)
            entries = entries.filter(
                feed__category=request.user.categories.get(name=name),
            )
        elif is_stream(stream, request.user.pk):
            state = is_stream(stream, request.user.pk)
            if state == 'read':  # mark read items as read yo
                return Response("OK")
            elif state in ['kept-unread', 'reading-list']:
                pass
            elif state in ['starred', 'broadcast']:
                entries = entries.filter(**{state: True})
            else:
                logger.info(u"Unknown state: {0}".format(state))
                return Response("OK")
        else:
            logger.info(u"Unknown stream: {0}".format(stream))
            return Response("OK")

        entries.filter(read=False).update(read=True)

        cursor = connection.cursor()
        cursor.execute("""
            update feeds_feed f set unread_count = (
                select count(*) from feeds_entry e
                where e.feed_id = f.id and read = false
            ) where f.user_id = %s
        """, [request.user.pk])
        return Response("OK")
mark_all_as_read = MarkAllAsRead.as_view()


class FriendList(ReaderView):
    def get(self, request, *args, **kwargs):
        return Response({
            'friends': [{
                'userIds': [str(request.user.pk)],
                'profileIds': [str(request.user.pk)],
                'contactId': '-1',
                'stream': u"user/{0}/state/com.google/broadcast".format(
                    request.user.pk),
                'flags': 1,
                'displayName': request.user.username,
                'givenName': request.user.username,
                'n': '',
                'p': '',
                'hasSharedItemsOnProfile': False,  # TODO handle broadcast
            }]
        })
friend_list = FriendList.as_view()


class OPMLExport(ReaderView):
    def get(self, request, *args, **kwargs):
        response = render(
            request, 'profiles/opml_export.opml',
            {'categories': request.user.categories.all(),
             'orphan_feeds': request.user.feeds.filter(category__isnull=True)})
        response['Content-Disposition'] = (
            'attachment; filename=feedhq-export.opml'
        )
        response['Content-Type'] = 'text/xml; charset=utf-8'
        return response
export_subscriptions = OPMLExport.as_view()


class OPMLImport(ReaderView):
    http_method_names = ['post']
    renderer_classes = [PlainRenderer]
    parser_classes = [XMLParser]
    require_post_token = False

    def post(self, request, *args, **kwargs):
        try:
            entries = opml.from_string(request.body)
        except XMLSyntaxError:
            raise exceptions.ParseError(
                "This file doesn't seem to be a valid OPML file.")

        existing_feeds = set(request.user.feeds.values_list('url', flat=True))
        try:
            with user_lock('opml_import', request.user.pk, timeout=30):
                imported = save_outline(request.user, None, entries,
                                        existing_feeds)
        except ValidationError:
            raise exceptions.ParseError(
                "Another concurrent OPML import is happening "
                "for this user.")
        return Response("OK: {0}".format(imported))
import_subscriptions = OPMLImport.as_view()
