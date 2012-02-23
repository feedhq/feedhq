import opml

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from django.views.generic import create_update

from ..decorators import login_required
from .models import Category, Feed, Entry
from .forms import CategoryForm, FeedForm, OPMLImportForm, ActionForm

"""
Each view displays a list of entries, with a level of filtering:
    - home: all entries
    - category: entries in a specific category
    - feed: entries for a specific feed
    - item: a single entry

Entries are paginated.
"""


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

    return paginated


@login_required
def feed_list(request, page=1, only_unread=False, category=None, feed=None):
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
    unread_count = entries.filter(read=False).count()

    # base_url is a variable that helps the paginator a lot. The drawback is
    # that the paginator can't use reversed URLs.
    base_url = all_url
    if only_unread:
        entries = entries.filter(read=False)
        base_url = unread_url
        entries = paginate(entries, page=page, force_count=unread_count,
                           nb_items=request.user.entries_per_page)
    else:
        entries = paginate(entries, page=page,
                           nb_items=request.user.entries_per_page)

    request.session['back_url'] = request.get_full_path()
    context = {
            'categories': categories,
            'category': category,
            'feed': feed,
            'entries': entries,
            'only_unread': only_unread,
            'unread_count': unread_count,
            'all_url': all_url,
            'unread_url': unread_url,
            'base_url': base_url,
    }
    if entries.paginator.count == 0 and Feed.objects.filter(
        category__in=request.user.categories.all()
    ).count() == 0:
        context['noob'] = True
    return render(request, 'feeds/feed_list.html', context)


@login_required
def add_category(request):
    """Add a category"""
    if request.method == 'POST':
        form = CategoryForm(data=request.POST)
        form.user = request.user
        if form.is_valid():
            category = Category(
                    name=form.cleaned_data['name'],
                    slug=form.slug,
                    user=request.user,
                    color=form.cleaned_data['color'],
                    delete_after=form.cleaned_data['delete_after'],
            )
            category.save()
            return redirect(reverse('feeds:category', args=[category.slug]))
    else:
        form = CategoryForm()

    context = {
            'form': form,
    }
    return render(request, 'feeds/category_form.html', context)


@login_required
def edit_category(request, slug):
    """Edit a category's details"""
    category = get_object_or_404(request.user.categories, slug=slug)
    if request.method == 'POST':
        form = CategoryForm(data=request.POST, instance=category)
        form.user = request.user
        if form.is_valid():
            form.save()
            messages.success(request, _('%(category)s has been successfully '
                                        'updated') % {'category': category})

    else:
        form = CategoryForm(instance=category)

    context = {
            'form': form,
            'category': category,
    }
    return render(request, 'feeds/edit_category.html', context)


@login_required
def delete_category(request, slug):
    """Delete the specified category"""
    cat = get_object_or_404(Category, slug=slug, user=request.user)
    url = reverse('feeds:home')
    feed_count = cat.feeds.count()
    entry_count = Entry.objects.filter(feed__category=cat).count()
    return create_update.delete_object(
        request, Category, object_id=cat.id, post_delete_redirect=url,
        extra_context={'entry_count': entry_count, 'feed_count': feed_count},
    )


@login_required
def add_feed(request):
    """Adds a Feed object"""
    if request.method == 'POST':
        form = FeedForm(data=request.POST)
        form.fields['category'].queryset = Category.objects.filter(\
                user=request.user)
        if form.is_valid():
            form.save()
            name = form.cleaned_data['name']
            messages.success(request, _('%(feed)s has been successfully '
                                        'added') % {'feed': name})
            category = form.cleaned_data['category']
            return redirect(category.get_absolute_url())
    else:
        form = FeedForm()
        form.fields['category'].queryset = Category.objects.filter(\
                user=request.user)

    context = {
            'form': form,
    }
    return render(request, 'feeds/feed_form.html', context)


@login_required
def edit_feed(request, feed):
    feed = get_object_or_404(Feed, category__user=request.user, pk=feed)
    if request.method == 'POST':
        form = FeedForm(data=request.POST, instance=feed)
        form.fields['category'].queryset = Category.objects.filter(\
                user=request.user)

        if form.is_valid():
            instance = form.save(commit=False)
            if not instance.override:
                instance.delete_after = ''
            instance.save()
            messages.success(request, _('%(feed)s has been successfully '
                                        'updated') % {'feed': feed})
            return redirect(reverse('feeds:feed', args=[instance.pk]))

    else:
        form = FeedForm(instance=feed)
        form.fields['category'].queryset = Category.objects.filter(\
                user=request.user)

    context = {
            'feed': feed,
            'form': form,
    }
    return render(request, 'feeds/edit_feed.html', context)


@login_required
def delete_feed(request, feed):
    feed = get_object_or_404(Feed, pk=feed, category__user=request.user)
    url = reverse('feeds:home')
    return create_update.delete_object(
        request, Feed, object_id=feed.id, post_delete_redirect=url,
        extra_context={'entry_count': feed.entries.count()},
    )


@login_required
def item(request, entry_id):
    qs = Entry.objects.filter(user=request.user).select_related(
        'feed', 'feed__category',
    )
    entry = get_object_or_404(qs, pk=entry_id)
    if not entry.read:
        Entry.objects.filter(pk=entry.pk).update(read=True)

    back_url = request.session.get('back_url',
                                   default=entry.feed.get_absolute_url())

    # Depending on the list used to access to this page, we try to find in an
    # intelligent way which is the previous and the next item in the list.

    # This way the user has nice 'previous' and 'next' buttons that are
    # dynamically changed
    showing_unread = False
    bits = back_url.split('/')
    # FIXME: The kw thing currently doesn't work with paginated content.
    kw = {'user': request.user}

    if bits[1] == '':
        # this is the homepage
        kw = {'user': request.user}

    elif bits[1] == 'unread':
        # Homepage too, but only unread
        kw = {'user': request.user, 'read': False}
        showing_unread = True

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
        showing_unread = True

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
    has_img = img_safe = False
    if '<img ' in entry.subtitle:
        has_img = True

    if request.method == 'POST':
        form = ActionForm(data=request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            if action == 'images':
                img_safe = True
            elif action == 'unread':
                Entry.objects.filter(pk=entry.pk).update(read=False)
                return redirect(back_url)
            elif action == 'images_always':
                Feed.objects.filter(pk=entry.feed.pk).update(img_safe=True)
                entry.feed.img_safe = True
            elif action == 'images_never':
                Feed.objects.filter(pk=entry.feed.pk).update(img_safe=False)
                entry.feed.img_safe = False

    context = {
        'category': entry.feed.category,
        'categories': request.user.categories.with_unread_counts(),
        'back_url': back_url,
        'showing_unread': showing_unread,
        'previous': previous,
        'next': next,
        'has_img': has_img,
        'img_safe': img_safe,
        'object': entry,
    }
    return render(request, 'feeds/entry_detail.html', context)


@login_required
def import_feeds(request):
    """Import feeds from an OPML source"""
    if request.method == 'POST':
        form = OPMLImportForm(request.POST, request.FILES)
        if form.is_valid():
            # get the list of existing feeds
            existing_feeds = [f.url for f in Feed.objects.filter(
                category__in=request.user.categories.all(),
            )]
            # try to get the "Unclassified" field, create it if needed
            category, created = request.user.categories.get_or_create(
                slug='imported', defaults={'name': _('Imported')},
            )

            entries = opml.parse(request.FILES['file'])
            imported = 0
            for entry in entries:
                if (hasattr(entry, 'xmlUrl') and
                    not entry.xmlUrl in existing_feeds):
                    feed = Feed(name=entry.title, url=entry.xmlUrl,
                            category=category)
                    setattr(feed, "skip_post_save", True)
                    feed.save()
                    imported += 1

            messages.success(
                request,
                _('%(num)s feeds have been imported' % {'num': imported}),
            )
            return redirect('feeds:home')

    else:
        form = OPMLImportForm()

    context = {
        'form': form,
    }
    return render(request, 'feeds/import_feeds.html', context)
