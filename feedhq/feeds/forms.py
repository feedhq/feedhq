from django import forms
from django.template.defaultfilters import slugify

from .models import Category, Feed


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        exclude = ('user', 'slug', 'order',)

    def clean_name(self):
        """Generates a slug and ensures it is unique for this user"""
        self.slug = slugify(self.cleaned_data['name'])
        valid = False
        while not valid:
            if self.slug in ('add', 'import'):  # gonna conflict
                self.slug = '%s-' % self.slug
            try:  # Maybe a category with this slug already exists...
                Category.objects.get(user=self.user, slug=self.slug)
                self.slug = self.slug + '-'
            except Category.DoesNotExist:  # ... or not
                valid = True
        return self.cleaned_data['name']


class FeedForm(forms.ModelForm):
    class Meta:
        model = Feed
        fields = ('name', 'url', 'category', 'muted', 'override',
                  'delete_after')


class OPMLImportForm(forms.Form):
    file = forms.FileField()


class ActionForm(forms.Form):
    action = forms.ChoiceField(choices=(
        ('images', 'images'),
        ('unread', 'unread'),
        ('images_always', 'images_always'),
        ('images_never', 'images_never'),
    ))


class ReadForm(forms.Form):
    action = forms.ChoiceField(choices=(
        ('read', 'read'),
    ), widget=forms.HiddenInput, initial='read')
