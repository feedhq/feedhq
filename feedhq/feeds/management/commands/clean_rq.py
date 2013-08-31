import datetime
import logging
import pytz

from dateutil import parser
from itertools import product

from . import SentryCommand
from ....utils import get_redis_connection

logger = logging.getLogger(__name__)


class Command(SentryCommand):
    def handle_sentry(self, **options):
        r = get_redis_connection()
        prefix = 'rq:job:'
        keys = (
            "".join(chars) for chars in product('0123456789abcdef', repeat=1)
        )
        delay = (
            datetime.datetime.utcnow().replace(tzinfo=pytz.utc) -
            datetime.timedelta(days=5)
        )
        count = 0
        for start in keys:
            prefix_keys = r.keys('{0}{1}*'.format(prefix, start))
            for key in prefix_keys:
                date = r.hget(key, 'created_at')
                if date is None:
                    continue
                date = parser.parse(date)
                if date < delay:
                    r.delete(key)
                    count += 1
        logger.info("Cleaned {0} jobs".format(count))
