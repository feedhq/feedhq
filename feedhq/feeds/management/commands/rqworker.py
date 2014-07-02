from optparse import make_option
import os

from raven import Client
from redis.exceptions import TimeoutError
from rq import Queue, Connection, Worker

from . import SentryCommand
from ....utils import get_redis_connection


def sentry_handler(job, *exc_info):
    if 'SENTRY_DSN' not in os.environ:
        # Use the next exception handler (send to failed queue)
        return True
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
    args = '<queue1 queue2 ...>'
    option_list = SentryCommand.option_list + (
        make_option('--burst', action='store_true', dest='burst',
                    default=False, help='Run the worker in burst mode'),
    )
    help = "Run a RQ worker on selected queues."
    ignore_exceptions = TimeoutError

    def handle_sentry(self, *args, **options):
        conn = get_redis_connection()
        with Connection(conn):
            queues = map(Queue, args)
            worker = Worker(queues, exc_handler=sentry_handler)
            worker.work(burst=options['burst'])
