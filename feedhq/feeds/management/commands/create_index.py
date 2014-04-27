from django.conf import settings
from django.core.management.base import BaseCommand

from .... import es


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        es.client.indices.create(settings.ES_INDEX, body={
            'mappings': {
                "entries": {
                    "_routing": {
                        "required": True,
                        "path": "user",
                    },
                    "properties": {
                        "timestamp": {
                            "format": "dateOptionalTime",
                            "type": "date"
                        },
                        "guid": {
                            "type": "string",
                            "index": "not_analyzed",
                        },
                        "raw_title": {
                            "type": "string",
                            "index": "not_analyzed",
                        },
                        "user": {
                            "type": "long",
                        },
                    },
                },
            },
        })
