from django.contrib.auth.models import User as DjangoUser
from django.db import models

from ..models import contribute_to_model


class User(models.Model):
    username = models.CharField(max_length=75, unique=True)

    class Meta:
        abstract = True

contribute_to_model(User, DjangoUser)
