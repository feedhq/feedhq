from optparse import make_option

from django.conf import settings
from django.core.management.base import BaseCommand

from redis import Redis
from rq import Queue, Connection, Worker


class Command(BaseCommand):
    args = '<queue1 queue2 ...>'
    option_list = BaseCommand.option_list + (
        make_option('--burst', action='store_true', dest='burst',
                    default=False, help='Run the worker in burst mode'),
    )
    help = "Run a RQ worker on selected queues."

    def handle(self, *args, **options):
        print settings.REDIS
        conn = Redis(**settings.REDIS)
        print conn
        with Connection(conn):
            queues = map(Queue, args)
            worker = Worker(queues)
            worker.work(burst=options['burst'])
