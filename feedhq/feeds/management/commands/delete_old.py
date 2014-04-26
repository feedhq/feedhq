from datetime import timedelta

from django.utils import timezone

from . import SentryCommand
from .... import es
from ....profiles.models import User


class Command(SentryCommand):
    def handle_sentry(self, **options):
        users = User.objects.all()
        for user in users:
            limit = timezone.now() - timedelta(days=user.ttl)
            if user.es:
                es.client.delete_by_query(
                    index=es.user_index(user.pk),
                    doc_type='entries',
                    body={'query': {'range': {'timestamp': {'lte': limit}}}},
                )
            else:
                user.entries.filter(date__lte=limit).delete()
