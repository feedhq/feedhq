import json
import logging
import re
from collections import defaultdict

import opml
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, InvalidPage, Paginator
from django.core.urlresolvers import reverse, reverse_lazy
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.template.defaultfilters import slugify
from django.utils.html import format_html
from django.utils.translation import ugettext as _, ungettext
from django.views import generic
from elasticsearch.exceptions import ConflictError, RequestError

from .forms import (ActionForm, CategoryForm, FeedForm, OPMLImportForm,
                    ReadForm, SubscriptionFormSet, UndoReadForm, user_lock)
from .models import Category, UniqueFeed
from .tasks import read_later
from .. import es
from ..decorators import login_required
from ..tasks import enqueue

"""
Each view displays a list of entries, with a level of filtering:
    - home: all entries
    - category: entries in a specific category
    - feed: entries for a specific feed
    - item: a single entry

Entries are paginated.
"""

logger = logging.getLogger(__name__)

MEDIA_RE = re.compile(
    r'.*<(img|audio|video|iframe|object|embed|script|source)\s+.*',
    re.UNICODE | re.DOTALL)


class Keyboard(generic.TemplateView):
    template_name = 'feeds/keyboard.html'
keyboard = Keyboard.as_view()


def paginate(object_list, page=1, nb_items=25, force_count=None):
    """
    Simple generic paginator for all the ``Entry`` lists
    """
    if force_count is not None:
        def count(x):
            return force_count
        object_list.count = count

    paginator = Paginator(object_list, nb_items)

    try:
        paginated = paginator.page(page)
    except (EmptyPage, InvalidPage):
        paginated = paginator.page(paginator.num_pages)

    return paginated, paginator._count


@login_required
def entries_list(request, page=1, mode=None, category=None, feed=None,
                 starred=False):
    """
    Displays a paginated list of entries.

    ``page``: the page number
    ``mode``: filters the list to display all / unread / starred items
    ``category``: (slug) if set, will filter the entries of this category
    ``feed``: (object_id) if set, will filter the entries of this feed

    Note: only set category OR feed. Not both at the same time.
    """
    page = int(page)
    user = request.user
    es_entries = es.manager.user(request.user).defer(
        'content', 'guid', 'tags', 'read_later_url',
        'author', 'broadcast', 'link', 'starred',
    ).query_aggregate('all_unread', read=False)
    if mode == 'unread':
        es_entries = es_entries.filter(read=False)
    elif mode == 'stars':
        es_entries = es_entries.filter(
            starred=True).query_aggregate('all_starred', starred=True)

    search = request.GET.get('q', '')
    if search:
        es_entries = es_entries.filter(query=search)

    if category is not None:
        category = get_object_or_404(user.categories, slug=category)
        all_url = reverse('feeds:category', args=[category.slug])
        unread_url = reverse('feeds:category', args=[category.slug, "unread"])
        stars_url = reverse('feeds:category', args=[category.slug, "stars"])
        es_entries = es_entries.filter(category=category.pk).query_aggregate(
            'all', category=category.pk).query_aggregate(
                'unread', category=category.pk, read=False)

    if feed is not None:
        feed = get_object_or_404(user.feeds.select_related('category'),
                                 pk=feed)
        all_url = reverse('feeds:feed', args=[feed.pk])
        unread_url = reverse('feeds:feed', args=[feed.pk, "unread"])
        stars_url = reverse('feeds:feed', args=[feed.pk, "stars"])

        category = feed.category
        es_entries = es_entries.filter(feed=feed.pk).query_aggregate(
            'all', feed=feed.pk).query_aggregate(
                'unread', feed=feed.pk, read=False)

    if starred is True:
        es_entries = es_entries.filter(starred=True).query_aggregate(
            'all', starred=True).query_aggregate(
                'unread', starred=True, read=False)
        all_url = reverse('feeds:entries', args=['stars'])
        unread_url = None
        stars_url = None

    if feed is None and category is None and starred is not True:
        all_url = reverse('feeds:entries')
        unread_url = reverse('feeds:entries', args=['unread'])
        stars_url = reverse('feeds:entries', args=['stars'])
        es_entries = es_entries.query_aggregate('all').query_aggregate(
            'unread', read=False)

    if user.oldest_first:
        es_entries = es_entries.order_by('timestamp', 'id')

    if request.method == 'POST':
        if request.POST['action'] in (ReadForm.READ_ALL, ReadForm.READ_PAGE):
            pages_only = request.POST['action'] == ReadForm.READ_PAGE
            form = ReadForm(es_entries, feed, category, user,
                            pages_only=pages_only, data=request.POST)
            if form.is_valid():
                pks = form.save()
                undo_form = loader.render_to_string('feeds/undo_read.html', {
                    'form': UndoReadForm(initial={
                        'pks': json.dumps(pks, separators=(',', ':'))}),
                    'action': request.get_full_path(),
                }, request=request)
                message = ungettext(
                    '1 entry has been marked as read.',
                    '%(value)s entries have been marked as read.',
                    len(pks)) % {'value': len(pks)}
                messages.success(request,
                                 format_html(u"{0} {1}", message, undo_form))

        elif request.POST['action'] == 'undo-read':
            form = UndoReadForm(user, data=request.POST)
            if form.is_valid():
                count = form.save()
                messages.success(
                    request, ungettext(
                        '1 entry has been marked as unread.',
                        '%(value)s entries have been marked as unread.',
                        count) % {'value': count})

        if mode == 'unread':
            return redirect(unread_url)
        elif mode == 'stars':
            return redirect(stars_url)
        else:
            return redirect(all_url)

    try:
        entries = es_entries.fetch(page=page,
                                   per_page=user.entries_per_page,
                                   annotate=user)
    except RequestError as e:
        if 'No mapping found' not in e.error:  # index is empty
            raise
        entries = []
        user._unread_count = unread_count = total_count = 0
    else:
        aggs = entries['aggregations']
        entries = entries['hits']
        unread_count = aggs['entries']['unread']['doc_count']
        total_count = aggs['entries']['all']['doc_count']
        user._unread_count = aggs['entries']['all_unread']['doc_count']
    if mode == 'unread':
        card = unread_count
    elif mode == 'stars':
        card = aggs['entries']['all_starred']['doc_count']
    else:
        card = total_count
    num_pages = card // user.entries_per_page
    if card % user.entries_per_page:
        num_pages += 1
    entries = {
        'object_list': entries,
        'paginator': {
            'num_pages': num_pages,
        },
        'has_previous': page > 1,
        'has_next': page < num_pages,
        'previous_page_number': page - 1,
        'next_page_number': page + 1,
        'number': page,
    }
    request.session['back_url'] = request.get_full_path()

    # base_url is a variable that helps the paginator a lot. The drawback is
    # that the paginator can't use reversed URLs.
    if mode == 'unread':
        base_url = unread_url
    elif mode == 'stars':
        base_url = stars_url
    else:
        base_url = all_url

    context = {
        'category': category,
        'feed': feed,
        'entries': entries,
        'mode': mode,
        'unread_count': unread_count,
        'total_count': total_count,
        'all_url': all_url,
        'unread_url': unread_url,
        'stars_url': stars_url,
        'base_url': base_url,
        'stars': starred,
        'all_unread': aggs['entries']['unread']['doc_count'],
        'entries_template': 'feeds/entries_include.html',
        'search': search,
        'search_form': True,
    }
    if unread_count:
        context['read_all_form'] = ReadForm()
        context['read_page_form'] = ReadForm(pages_only=True, initial={
            'action': ReadForm.READ_PAGE,
            'pages': json.dumps([int(page)]),
        })
        context['action'] = request.get_full_path()
    if (
        len(entries['object_list']) == 0 and
        request.user.feeds.count() == 0
    ):
        context['noob'] = True

    if request.is_ajax():
        template_name = context['entries_template']
    else:
        template_name = 'feeds/entries_list.html'

    return render(request, template_name, context)


class SuccessMixin(object):
    success_message = None

    def get_success_message(self):
        return self.success_message

    def form_valid(self, form):
        response = super(SuccessMixin, self).form_valid(form)
        msg = self.get_success_message()
        if msg is not None:
            messages.success(self.request, msg)
        return response


class CategoryMixin(SuccessMixin):
    form_class = CategoryForm
    success_url = reverse_lazy('feeds:manage')

    def get_form_kwargs(self):
        kwargs = super(CategoryMixin, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_object(self):
        return get_object_or_404(self.request.user.categories,
                                 slug=self.kwargs['slug'])


class AddCategory(CategoryMixin, generic.CreateView):
    template_name = 'feeds/category_form.html'
add_category = login_required(AddCategory.as_view())


class EditCategory(CategoryMixin, generic.UpdateView):
    template_name = 'feeds/edit_category.html'

    def get_success_message(self):
        return _('%(category)s has been successfully '
                 'updated') % {'category': self.object}
edit_category = login_required(EditCategory.as_view())


class DeleteCategory(CategoryMixin, generic.DeleteView):
    success_url = reverse_lazy('feeds:manage')

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        pk = self.object.pk
        name = self.object.name
        self.object.delete()
        request.user.delete_category_entries(pk)
        messages.success(
            self.request,
            _('%(category)s has been successfully deleted') % {
                'category': name})
        success_url = self.get_success_url()
        return redirect(success_url)

    def get_context_data(self, **kwargs):
        entry_count = es.client.count(
            index=es.user_alias(self.request.user.pk),
            doc_type='entries',
            body={
                'query': {
                    'filtered': {
                        'filter': {'term': {'category': self.object.pk}},
                    },
                },
            },
        )['count']
        kwargs.update({
            'entry_count': entry_count,
            'feed_count': self.object.feeds.count(),
        })
        return super(DeleteCategory, self).get_context_data(**kwargs)
delete_category = login_required(DeleteCategory.as_view())


class FeedMixin(SuccessMixin):
    form_class = FeedForm
    success_url = reverse_lazy('feeds:manage')

    def get_form_kwargs(self):
        kwargs = super(FeedMixin, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_object(self):
        return get_object_or_404(self.request.user.feeds,
                                 pk=self.kwargs['feed'])


class AddFeed(FeedMixin, generic.CreateView):
    template_name = 'feeds/feed_form.html'

    def get_success_message(self):
        return _('%(feed)s has been successfully '
                 'added') % {'feed': self.object.name}

    def get_initial(self):
        initial = super(AddFeed, self).get_initial()
        if 'feed' in self.request.GET:
            initial['url'] = self.request.GET['feed']
        if 'name' in self.request.GET:
            initial['name'] = self.request.GET['name']
        return initial
add_feed = login_required(AddFeed.as_view())


class EditFeed(FeedMixin, generic.UpdateView):
    template_name = 'feeds/edit_feed.html'

    def get_success_message(self):
        return _('%(feed)s has been successfully '
                 'updated') % {'feed': self.object.name}
edit_feed = login_required(EditFeed.as_view())


class DeleteFeed(FeedMixin, generic.DeleteView):
    def get_context_data(self, **kwargs):
        entry_count = es.client.count(
            index=es.user_alias(self.request.user.pk),
            doc_type='entries',
            body={
                'query': {
                    'filtered': {
                        'filter': {'term': {'feed': self.object.pk}},
                    },
                },
            },
        )['count']
        kwargs['entry_count'] = entry_count
        return super(DeleteFeed, self).get_context_data(**kwargs)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        pk = self.object.pk
        name = self.object.name
        self.object.delete()
        request.user.delete_feed_entries(pk)
        messages.success(
            request,
            _('%(feed)s has been successfully deleted') % {
                'feed': name})
        success_url = self.get_success_url()
        return redirect(success_url)
delete_feed = login_required(DeleteFeed.as_view())


@login_required
def item(request, entry_id):
    entry = es.entry(request.user, entry_id)
    if not entry.read:
        try:
            entry.update(read=True)
        except ConflictError:
            # Double click // two operations at a time. Entry has already
            # been marked as read.
            pass
    back_url = request.session.get('back_url',
                                   default=entry.feed.get_absolute_url())

    # Depending on the list used to access to this page, we try to find in an
    # intelligent way which is the previous and the next item in the list.

    # This way the user has nice 'previous' and 'next' buttons that are
    # dynamically changed
    mode = None
    bits = back_url.split('/')
    # FIXME: The kw thing currently doesn't work with paginated content.
    kw = {'user': request.user}

    if bits[1] == 'unread':
        # only unread
        kw['read'] = False
        mode = 'unread'

    elif bits[1] == 'stars':
        mode = 'stars'
        kw['starred'] = True

    elif bits[1] == 'feed':
        # Entries in self.feed
        kw = {'feed': entry.feed}

    elif bits[1] == 'category':
        # Entries in self.feed.category
        category_slug = bits[2]
        category = Category.objects.get(slug=category_slug, user=request.user)
        kw = {'feed__category': category}

    if len(bits) > 3:
        if bits[3] == 'unread':
            kw['read'] = False
            mode = 'unread'
        elif bits[3] == 'stars':
            kw['starred'] = True

    # The previous is actually the next by date, and vice versa
    es_entries = es.manager.user(request.user).exclude(id=entry.pk)
    if 'feed' in kw:
        es_entries = es_entries.filter(feed=kw['feed'].pk)
    if 'read' in kw:
        es_entries = es_entries.filter(read=kw['read'])
    if 'feed__category' in kw:
        es_entries = es_entries.filter(category=kw['feed__category'].pk)
    if 'starred' in kw:
        es_entries = es_entries.filter(starred=kw['starred'])
    previous = es_entries.filter(timestamp__gte=entry.date).order_by(
        'timestamp', 'id').fetch(per_page=1)
    previous = previous['hits'][0] if previous['hits'] else None
    if previous is not None:
        if previous.date == entry.date:
            previous = es_entries.filter(
                timestamp__gte=entry.date).filter(
                id__gt=entry.pk
            ).order_by('timestamp', 'id').fetch(per_page=1)
            previous = previous['hits'][0] if previous['hits'] else None
        if previous is not None:
            previous = previous.get_absolute_url()
    next = es_entries.filter(timestamp__lte=entry.date).order_by(
        '-timestamp', '-id').fetch(per_page=1)
    next = next['hits'][0] if next['hits'] else None
    if next is not None:
        if next.date == entry.date:
            next = es_entries.filter(
                timestamp__lte=entry.date).filter(
                id__lt=entry.pk
            ).order_by('-timestamp', '-id').fetch(per_page=1)
            next = next['hits'][0] if next['hits'] else None
        if next is not None:
            next = next.get_absolute_url()

    if request.user.oldest_first:
        previous, next = next, previous

    # if there is an image in the entry, don't show it. We need user
    # intervention to display the image.
    has_media = media_safe = False
    if MEDIA_RE.match(entry.subtitle):
        has_media = True

    if request.method == 'POST':
        form = ActionForm(data=request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            if action == 'images':
                if 'never' in request.POST:
                    entry.feed.img_safe = False
                    entry.feed.save(update_fields=['img_safe'])
                elif 'once' in request.POST:
                    media_safe = True
                elif 'always' in request.POST:
                    entry.feed.img_safe = True
                    entry.feed.save(update_fields=['img_safe'])
            elif action == 'unread':
                entry.update(read=False, refresh=True)
                return redirect(back_url)
            elif action == 'read_later':
                enqueue(read_later, args=[request.user.pk, entry.pk],
                        timeout=20, queue='high')
                messages.success(
                    request,
                    _('Article successfully added to your reading list'),
                )
            elif action in ['star', 'unstar']:
                entry.update(starred=action == 'star', refresh=True)

    context = {
        'category': entry.feed.category,
        'back_url': back_url,
        'mode': mode,
        'previous': previous,
        'next': next,
        'has_media': has_media,
        'media_safe': media_safe,
        'object': entry,
    }
    return render(request, 'feeds/entry_detail.html', context)


def truncate(value, length):
    if len(value) > length - 3:
        value = value[:length - 3] + '...'
    return value


def save_outline(user, category, outline, existing):
    count = 0
    try:
        opml_tag = outline._tree.getroot().tag == 'opml'
    except AttributeError:
        opml_tag = False
    if (
        not hasattr(outline, 'xmlUrl') and
        hasattr(outline, 'title') and
        outline._outlines
    ):
        if opml_tag:
            cat = None
            created = False
        else:
            slug = slugify(outline.title)
            if not slug:
                slug = 'unknown'
            title = truncate(outline.title, 1023)
            slug = slug[:50]
            cat, created = user.categories.get_or_create(
                slug=slug, defaults={'name': title},
            )
        for entry in outline._outlines:
            count += save_outline(user, cat, entry, existing)
        if created and cat.feeds.count() == 0:
            cat.delete()

    for entry in outline:
        count += save_outline(user, category, entry, existing)

    if (hasattr(outline, 'xmlUrl')):
        if outline.xmlUrl not in existing:
            existing.add(outline.xmlUrl)
            title = getattr(outline, 'title',
                            getattr(outline, 'text', _('No title')))
            title = truncate(title, 1023)
            user.feeds.create(category=category, url=outline.xmlUrl,
                              name=title)
            count += 1
    return count


@login_required
@transaction.atomic
def import_feeds(request):
    """Import feeds from an OPML source"""
    if request.method == 'POST':
        form = OPMLImportForm(request.POST, request.FILES)
        if form.is_valid():
            # get the list of existing feeds
            existing_feeds = set(request.user.feeds.values_list('url',
                                                                flat=True))

            entries = opml.parse(request.FILES['file'])
            try:
                with user_lock('opml_import', request.user.pk, timeout=30):
                    imported = save_outline(request.user, None, entries,
                                            existing_feeds)
            except ValidationError:
                logger.info("Prevented duplicate import for user %s",
                            request.user.pk)
            else:
                message = " ".join([ungettext(
                    u'%s feed has been imported.',
                    u'%s feeds have been imported.',
                    imported) % imported,
                    _('New content will appear in a moment when you refresh '
                      'the page.')
                ])
                messages.success(request, message)
                return redirect('feeds:entries')

    else:
        form = OPMLImportForm()

    context = {
        'form': form,
    }
    return render(request, 'feeds/import_feeds.html', context)


@login_required
def dashboard(request, mode=None):
    categories = request.user.categories.values()
    feeds = request.user.feeds.all()

    for cat in categories:
        cat['unread_count'] = 0

    feed_to_cat = {feed.pk: feed.category_id for feed in feeds}

    category_feeds = defaultdict(list)
    category_counts = defaultdict(int)

    counts = es.counts(request.user, feed_to_cat.keys(), stars=mode == 'stars')
    _all = 0
    for feed in feeds:
        feed.unread_count = counts[str(feed.pk)][str(feed.pk)]['doc_count']
        _all += feed.unread_count
        if feed.category_id is None:
            continue
        category_feeds[feed.category_id].append(feed)
        category_counts[feed.category_id] += feed.unread_count

    for c in categories:
        c['unread_count'] = category_counts[c['id']]
        c['feeds'] = {'all': category_feeds[c['id']]}

    uncategorized = [feed for feed in feeds if feed.category_id is None]
    for feed in uncategorized:
        feed.unread_count = counts[str(feed.pk)][str(feed.pk)]['doc_count']

    if mode == 'unread':
        categories = [c for c in categories if c['unread_count']]

        for c in categories:
            c['feeds'] = {'all': [feed for feed in c['feeds']['all']
                                  if feed.unread_count]}
        uncategorized = [feed for feed in uncategorized
                         if feed.unread_count]
    total = len(uncategorized) + sum(
        (len(c['feeds']['all']) for c in categories)
    )

    has_orphans = bool(len(uncategorized))

    if has_orphans:
        categories = [
            {'feeds': {'all': uncategorized}}
        ] + list(categories)

    col_size = total // 3
    col_1 = None
    col_2 = None
    done = len(uncategorized)
    for index, cat in enumerate(categories[has_orphans:]):
        if col_1 is None and done > col_size:
            col_1 = index + 1
        if col_2 is None and done > 2 * col_size:
            col_2 = index + 1
        done += len(cat['feeds']['all'])

    context = {
        'categories': categories,
        'breaks': [col_1, col_2],
        'mode': mode,
    }
    return render(request, 'feeds/dashboard.html', context)


class Subscribe(generic.FormView):
    form_class = SubscriptionFormSet
    template_name = 'feeds/subscribe.html'

    def get_initial(self):
        urls = [l for l in self.request.GET.get('feeds', '').split(',') if l]
        self.feed_count = len(urls)

        self.existing = self.request.user.feeds.filter(url__in=urls)

        existing_urls = set([e.url for e in self.existing])

        new_urls = [url for url in urls if url not in existing_urls]
        name_prefill = {}
        if new_urls:
            uniques = UniqueFeed.objects.filter(
                url__in=new_urls)
            for unique in uniques:
                name_prefill[unique.url] = unique.job_details.get('title')

        return [{
            'name': name_prefill.get(url),
            'url': url,
            'subscribe': True,
        } for url in new_urls]

    def get_form(self, form_class=None):
        formset = super(Subscribe, self).get_form(form_class)
        cats = [['', '-----']] + [
            (str(c.pk), c.name) for c in self.request.user.categories.all()
        ]
        for form in formset:
            form.fields['category'].choices = cats
            form.user = self.request.user
        return formset

    def get_context_data(self, **kwargs):
        ctx = super(Subscribe, self).get_context_data(**kwargs)
        ctx['site_url'] = self.request.GET.get('url')
        return ctx

    def form_valid(self, formset):
        created = 0
        for form in formset:
            if form.cleaned_data['subscribe']:
                if form.cleaned_data['category']:
                    category = self.request.user.categories.get(
                        pk=form.cleaned_data['category'],
                    )
                else:
                    category = None
                self.request.user.feeds.create(
                    name=form.cleaned_data['name'],
                    url=form.cleaned_data['url'],
                    category=category,
                )
                created += 1
        if created == 1:
            message = _('1 feed has been added')
        else:
            message = _('%s feeds have been added') % created
        messages.success(self.request, message)
        return redirect(reverse('feeds:entries'))
subscribe = login_required(Subscribe.as_view())


class ManageFeeds(generic.TemplateView):
    template_name = 'feeds/manage_feeds.html'

    def get_context_data(self, **kwargs):
        ctx = super(ManageFeeds, self).get_context_data(**kwargs)
        feeds = self.request.user.feeds.select_related('category').order_by(
            'category__name', 'category__id', 'name',
        ).extra(select={
            'muted': """
                select muted from feeds_uniquefeed
                where feeds_uniquefeed.url = feeds_feed.url
            """,
            'error': """
                select muted_reason from feeds_uniquefeed
                where feeds_uniquefeed.url = feeds_feed.url
            """,
        })

        ctx['feeds'] = feeds
        return ctx
manage = login_required(ManageFeeds.as_view())
