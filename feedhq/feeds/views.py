import opml
import re

from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.core.urlresolvers import reverse, reverse_lazy
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext as _
from django.views import generic

from ..decorators import login_required
from ..tasks import enqueue
from .models import Category, Feed, Entry, UniqueFeed
from .forms import (CategoryForm, FeedForm, OPMLImportForm, ActionForm,
                    ReadForm, SubscriptionFormSet)
from .tasks import read_later

"""
Each view displays a list of entries, with a level of filtering:
    - home: all entries
    - category: entries in a specific category
    - feed: entries for a specific feed
    - item: a single entry

Entries are paginated.
"""

MEDIA_RE = re.compile(r'.*<(img|audio|video)\s+.*', re.UNICODE | re.DOTALL)


def paginate(object_list, page=1, nb_items=25, force_count=None):
    """
    Simple generic paginator for all the ``Entry`` lists
    """
    if force_count is not None:
        object_list.count = lambda x: force_count

    paginator = Paginator(object_list, nb_items)

    try:
        paginated = paginator.page(page)
    except (EmptyPage, InvalidPage):
        paginated = paginator.page(paginator.num_pages)

    return paginated, paginator._count


@login_required
def entries_list(request, page=1, only_unread=False, category=None, feed=None):
    """
    Displays a paginated list of entries.

    ``page``: the page number
    ``only_unread``: filters the list to display only the new entries
    ``category``: (slug) if set, will filter the entries of this category
    ``feed``: (object_id) if set, will filter the entries of this feed

    Note: only set category OR feed. Not both at the same time.
    """
    user = request.user
    # Filtering the categories only to those owned by this user
    categories = user.categories.with_unread_counts()

    if category is not None:
        category = get_object_or_404(user.categories.all(), slug=category)
        entries = user.entries.filter(feed__category=category)
        all_url = reverse('feeds:category', args=[category.slug])
        unread_url = reverse('feeds:unread_category', args=[category.slug])

    if feed is not None:
        cat_ids = [c['id'] for c in categories]
        feed = get_object_or_404(Feed.objects.select_related('category'),
                                 category__in=cat_ids, pk=feed)
        entries = feed.entries.all()
        all_url = reverse('feeds:feed', args=[feed.id])
        unread_url = reverse('feeds:unread_feed', args=[feed.id])
        category = feed.category

    if feed is None and category is None:
        entries = user.entries.all()
        all_url = reverse('feeds:home')
        unread_url = reverse('feeds:unread')

    entries = entries.select_related('feed', 'feed__category')

    if request.method == "POST":
        form = ReadForm(data=request.POST)
        if form.is_valid():
            count = entries.filter(read=False).count()
            entries.update(read=True)
            if feed is not None:
                feeds = Feed.objects.filter(pk=feed.pk)
            elif category is not None:
                feeds = category.feeds.all()
            else:
                feeds = Feed.objects.filter(category__user=user)
            feeds.update(unread_count=0)
            messages.success(request,
                             _('%s entries have been marked as read' % count))
            if only_unread:
                return redirect(unread_url)
            else:
                return redirect(all_url)

    unread_count = entries.filter(read=False).count()

    # base_url is a variable that helps the paginator a lot. The drawback is
    # that the paginator can't use reversed URLs.
    base_url = all_url
    if only_unread:
        total_count = entries.count()
        entries = entries.filter(read=False)
        base_url = unread_url
        entries, foo = paginate(entries, page=page,
                                force_count=unread_count,
                                nb_items=request.user.entries_per_page)
    else:
        entries, total_count = paginate(entries, page=page,
                                        nb_items=request.user.entries_per_page)

    request.session['back_url'] = request.get_full_path()
    context = {
        'categories': categories,
        'category': category,
        'feed': feed,
        'entries': entries,
        'only_unread': only_unread,
        'unread_count': unread_count,
        'total_count': total_count,
        'all_url': all_url,
        'unread_url': unread_url,
        'base_url': base_url,
    }
    if unread_count:
        context['form'] = ReadForm()
        context['action'] = request.get_full_path()
    if entries.paginator.count == 0 and Feed.objects.filter(
        category__in=request.user.categories.all()
    ).count() == 0:
        context['noob'] = True
    return render(request, 'feeds/entries_list.html', context)


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

    def get_form_kwargs(self):
        kwargs = super(CategoryMixin, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse('feeds:category', args=[self.object.slug])

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
    def get_success_url(self):
        messages.success(self.request,
                         _('%(category)s has been successfully '
                           'deleted') % {'category': self.object})
        return reverse('feeds:home')

    def get_context_data(self, **kwargs):
        kwargs.update({
            'entry_count': Entry.objects.filter(
                feed__category=self.object,
            ).count(),
            'feed_count': self.object.feeds.count(),
        })
        return super(DeleteCategory, self).get_context_data(**kwargs)
delete_category = login_required(DeleteCategory.as_view())


class FeedMixin(SuccessMixin):
    form_class = FeedForm

    def get_form_kwargs(self):
        kwargs = super(FeedMixin, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_object(self):
        return get_object_or_404(Feed, category__user=self.request.user,
                                 pk=self.kwargs['feed'])

    def get_success_url(self):
        return reverse('feeds:category', args=[self.object.category.slug])


class AddFeed(FeedMixin, generic.CreateView):
    template_name = 'feeds/feed_form.html'

    def form_valid(self, form):
        response = super(AddFeed, self).form_valid(form)
        messages.success(self.request, _('%(feed)s has been successfully '
                                         'added') % {'feed': self.object.name})
        return response

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

    def form_valid(self, form):
        response = super(EditFeed, self).form_valid(form)
        messages.success(
            self.request, _('%(feed)s has been successfully '
                            'updated') % {'feed': self.object.name})
        return response
edit_feed = login_required(EditFeed.as_view())


class DeleteFeed(generic.DeleteView):
    def get_success_url(self):
        messages.success(
            self.request, _('%(feed)s has been successfully '
                            'deleted') % {'feed': self.object.name})
        return reverse_lazy('feeds:home')

    def get_object(self):
        return get_object_or_404(Feed,
                                 pk=self.kwargs['feed'],
                                 category__user=self.request.user)

    def get_context_data(self, **kwargs):
        kwargs['entry_count'] = self.object.entries.count()
        return super(DeleteFeed, self).get_context_data(**kwargs)
delete_feed = login_required(DeleteFeed.as_view())


@login_required
def item(request, entry_id):
    qs = Entry.objects.filter(user=request.user).select_related(
        'feed', 'feed__category',
    )
    entry = get_object_or_404(qs, pk=entry_id)
    if not entry.read:
        entry.read = True
        entry.save(update_fields=['read'])
        entry.feed.update_unread_count()

    back_url = request.session.get('back_url',
                                   default=entry.feed.get_absolute_url())

    # Depending on the list used to access to this page, we try to find in an
    # intelligent way which is the previous and the next item in the list.

    # This way the user has nice 'previous' and 'next' buttons that are
    # dynamically changed
    only_unread = False
    bits = back_url.split('/')
    # FIXME: The kw thing currently doesn't work with paginated content.
    kw = {'user': request.user}

    if bits[1] == '':
        # this is the homepage
        kw = {'user': request.user}

    elif bits[1] == 'unread':
        # Homepage too, but only unread
        kw = {'user': request.user, 'read': False}
        only_unread = True

    elif bits[1] == 'feed':
        # Entries in self.feed
        kw = {'feed': entry.feed}

    elif bits[1] == 'category':
        # Entries in self.feed.category
        category_slug = bits[2]
        category = Category.objects.get(slug=category_slug, user=request.user)
        kw = {'feed__category': category}

    if len(bits) > 3 and bits[3] == 'unread':
        kw['read'] = False
        only_unread = True

    # The previous is actually the next by date, and vice versa
    try:
        previous = entry.get_next_by_date(**kw).get_absolute_url()
    except entry.DoesNotExist:
        previous = None
    try:
        next = entry.get_previous_by_date(**kw).get_absolute_url()
    except entry.DoesNotExist:
        next = None

    # For serch results, previous and next aren't available
    if bits[1] == 'search':
        previous = None
        next = None

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
                entry.read = False
                entry.save(update_fields=['read'])
                entry.feed.update_unread_count()
                return redirect(back_url)
            elif action == 'read_later':
                enqueue(read_later, args=[entry.pk], timeout=20, queue='high')
                messages.success(
                    request,
                    _('Article successfully added to your reading list'),
                )

    context = {
        'category': entry.feed.category,
        'categories': request.user.categories.with_unread_counts(),
        'back_url': back_url,
        'only_unread': only_unread,
        'previous': previous,
        'next': next,
        'has_media': has_media,
        'media_safe': media_safe,
        'object': entry,
    }
    return render(request, 'feeds/entry_detail.html', context)


def save_outline(user, category, outline, existing):
    count = 0
    if (
        not hasattr(outline, 'xmlUrl') and
        hasattr(outline, 'title') and
        outline._outlines
    ):
        slug = slugify(outline.title)
        if not slug:
            slug = 'unknown'
        title = outline.title
        if len(title) > 1023:
            title = title[:1020] + '...'
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
            category.feeds.create(url=outline.xmlUrl,
                                  name=title)
            count += 1
    return count


@login_required
@transaction.commit_on_success
def import_feeds(request):
    """Import feeds from an OPML source"""
    if request.method == 'POST':
        form = OPMLImportForm(request.POST, request.FILES)
        if form.is_valid():
            # get the list of existing feeds
            existing_feeds = set([f.url for f in Feed.objects.filter(
                category__in=request.user.categories.all(),
            )])
            # try to get the "Unclassified" field, create it if needed
            category, created = request.user.categories.get_or_create(
                slug='imported', defaults={'name': _('Imported')},
            )

            entries = opml.parse(request.FILES['file'])
            imported = save_outline(request.user, category, entries,
                                    existing_feeds)

            if created and category.feeds.count() == 0:
                category.delete()

            messages.success(
                request,
                _('%(num)s feeds have been imported, new content will appear '
                  'in a moment when you refresh the '
                  'page.' % {'num': imported}),
            )
            return redirect('feeds:home')

    else:
        form = OPMLImportForm()

    context = {
        'form': form,
    }
    return render(request, 'feeds/import_feeds.html', context)


@login_required
def dashboard(request):
    categories = Category.objects.prefetch_related(
        'feeds',
    ).filter(user=request.user).annotate(
        unread_count=Sum('feeds__unread_count'),
    )

    total = sum((len(c.feeds.all()) for c in categories))
    col_size = total / 3
    col_1 = None
    col_2 = None
    done = 0
    for index, cat in enumerate(categories):
        done += len(cat.feeds.all())
        if col_1 is None and done > col_size:
            col_1 = index + 1
        if col_2 is None and done > 2 * col_size:
            col_2 = index + 1
    context = {
        'categories': categories,
        'breaks': [col_1, col_2],
    }
    return render(request, 'feeds/dashboard.html', context)


class Subscribe(generic.FormView):
    form_class = SubscriptionFormSet
    template_name = 'feeds/subscribe.html'

    def get_initial(self):
        urls = [l for l in self.request.GET.get('feeds', '').split(',') if l]
        self.feed_count = len(urls)

        self.existing = Feed.objects.filter(
            category__user=self.request.user,
            url__in=urls)

        existing_urls = set([e.url for e in self.existing])

        new_urls = [url for url in urls if not url in existing_urls]
        name_prefill = {}
        if new_urls:
            uniques = UniqueFeed.objects.filter(
                url__in=new_urls).values_list('title', 'url')
            for title, url in uniques:
                name_prefill[url] = title

        return [{
            'name': name_prefill.get(url),
            'url': url,
            'subscribe': True,
        } for url in new_urls]

    def get_form(self, form_class):
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
                category = self.request.user.categories.get(
                    pk=form.cleaned_data['category'],
                )
                category.feeds.create(name=form.cleaned_data['name'],
                                      url=form.cleaned_data['url'])
                created += 1
        if created == 1:
            message = _('1 feed has been added')
        else:
            message = _('%s feeds have been added') % created
        messages.success(self.request, message)
        return redirect(reverse('feeds:home'))
subscribe = login_required(Subscribe.as_view())
