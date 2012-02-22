from django.db import models
from django.utils.functional import curry


def contribute_to_model(contrib, destination):
    """
    Update ``contrib`` model based on ``destination``.

    Every new field will be created. Existing fields will have some properties
    updated.

    Methods and properties of ``contrib`` will populate ``destination``.

    Usage example:

    >>> from django.contrib.auth.models import User
    >>> from django.db import models
    >>>
    >>> class MyUser(models.Model):
    ...     class Meta:
    ...         abstract = True
    ...         db_table = 'user' # new auth_user table name
    ...
    ...     # New field
    ...     phone = models.CharField('phone number', blank=True, max_length=20)
    ...
    ...     # Email could be null
    ...     email = models.EmailField(blank=True, null=True)
    ...
    ...     # New (stupid) method
    ...     def get_phone(self):
    ...         return self.phone
    ...
    >>> contribute_to_model(MyUser, User)
    """

    # Contrib should be abstract
    if not contrib._meta.abstract:
        raise ValueError('Your contrib model should be abstract.')

    protected_get_display_method = []
    # Update or create new fields
    for field in contrib._meta.fields:
        try:
            destination._meta.get_field_by_name(field.name)
        except models.FieldDoesNotExist:
            field.contribute_to_class(destination, field.name)
            if field.choices:
                setattr(destination, 'get_%s_display' % field.name,
                        curry(destination._get_FIELD_display, field=field))
                protected_get_display_method.append(
                    'get_%s_display' % field.name
                )

        else:
            current_field = destination._meta.get_field_by_name(field.name)[0]
            current_field.null = field.null
            current_field.blank = field.blank
            current_field.max_length = field.max_length
            current_field._unique = field.unique

    # Change some meta information
    if hasattr(contrib.Meta, 'db_table'):
        destination._meta.db_table = contrib._meta.db_table

    # Add (or replace) properties and methods
    protected_items = (dir(models.Model) + ['Meta', '_meta'] +
                       protected_get_display_method)
    for k, v in contrib.__dict__.items():
        if k not in protected_items:
            setattr(destination, k, v)
