from django.conf import settings
from django.core.management.base import BaseCommand

from .... import es


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        es.client.indices.create(settings.ES_INDEX, body={
            'settings': {
                'index': {
                    'number_of_shards': settings.ES_SHARDS,
                    'number_of_replicas': settings.ES_REPLICAS,
                },
            },
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
