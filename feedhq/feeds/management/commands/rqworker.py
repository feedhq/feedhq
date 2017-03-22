import os

from raven import Client
from rq import Connection, Queue, Worker

from . import SentryCommand
from ....utils import get_redis_connection


def sentry_handler(job, *exc_info):
    if 'SENTRY_DSN' not in os.environ:
        # Don't escalate to other handlers
        return False
    client = Client()
    client.captureException(
        exc_info=exc_info,
        extra={
            'job_id': job.id,
            'func': job.func,
            'args': job.args,
            'kwargs': job.kwargs,
            'description': job.description,
        },
    )
    return False


class Command(SentryCommand):
    help = "Run a RQ worker on selected queues."

    def add_arguments(self, parser):
        parser.add_argument('queues', nargs='+')
        parser.add_argument('--burst', dest='burst', action='store_true',
                            default=False,
                            help='Run the worker in burst mode')

    def handle_sentry(self, *args, **options):
        conn = get_redis_connection()
        with Connection(conn):
            queues = map(Queue, options['queues'])
            worker = Worker(queues, exception_handlers=[sentry_handler])
            worker.work(burst=options['burst'])
