import logging.config
import os

import logging_tree

from structlog import configure, dev, get_logger, processors, stdlib


class StructlogHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log = get_logger()

    def emit(self, record):
        kw = {k: getattr(record, k) for k in {'exc_info', 'exc_text', 'args'}
              if getattr(record, k)}
        try:
            message = record.msg % record.args
        except TypeError:
            message = record.msg
        if len(message) > 100:
            message = message[:100] + ' [TRUNCATED]'
        kw['full_message'] = message
        self._log.log(record.levelno, record.msg,
                      logger_name=record.name, **kw)


def fix_logger_name(logger, method_name, event_dict):
    """
    Captured stdlib logging messages have logger=feedhq.logging and
    logger_name=original_logger_name. Overwrite logger with correct name.
    """
    if 'logger_name' in event_dict:
        event_dict['logger'] = event_dict.pop('logger_name')
    return event_dict


OBFUSCATE_HEADERS = {'Authorization', 'Cookie'}


def get_headers(request, obfuscate=OBFUSCATE_HEADERS):
    headers = {k for k in request.META if k.startswith('HTTP_')}
    pretty_headers = {}
    for header in headers:
        key = "-".join([
            w.capitalize() for w in header[len('HTTP_'):].split('_')
        ])
        pretty_headers[key] = request.META[header]
    for key in set(pretty_headers.keys()).intersection(obfuscate):
        if pretty_headers[key]:
            pretty_headers[key] = '**********'
        else:
            pretty_headers.pop(key)
    for key in ['Content-Type', 'Content-Length']:
        meta_key = key.upper().replace('-', '_')
        if meta_key in request.META:
            pretty_headers[key] = request.META[meta_key]
    return pretty_headers


def format_request(logger, method_name, event_dict):
    """Add request attrs when available:
        - URL
        - headers
        - querystring
        - User info
        - JSON/POST data
    """
    if 'request' in event_dict:
        req = event_dict['request']
        # Can't rely on instance checks because django's http request must
        # not be imported too soon.
        if 'rest_framework.request.Request' in str(type(req)):
            event_dict['request'] = {
                'method': req.method,
                'headers': get_headers(req),
                'path': req.path,
                'querystring': req.query_params,
                'user_id': req.user.pk,
            }
        elif 'django.http.request.HttpRequest' in str(type(req)):
            event_dict['request'] = {
                'method': req.method,
                'headers': get_headers(req),
                'path': req.path,
                'querystring': dict(req.GET),
                'user_id': req.user.pk,
            }
    return event_dict


def ensure_event(_, __, event_dict):
    event_dict.setdefault('event', '(no message)')
    return event_dict


def logstash_processor(_, __, event_dict):
    """
    Adds @version field for Logstash.
    Puts event in a 'message' field.
    Serializes timestamps in ISO format.
    """
    if 'message' in event_dict and 'full_message' not in event_dict:
        event_dict['full_message'] = event_dict['message']
    event_dict['message'] = event_dict.pop('event', '')
    for key, value in event_dict.items():
        if hasattr(value, 'isoformat') and callable(value.isoformat):
            event_dict[key] = value.isoformat() + 'Z'
    event_dict['@version'] = 1
    event_dict['_type'] = event_dict['type'] = 'feedhq'
    return event_dict


def add_syslog_program(syslog):
    pid = os.getpid()

    def renderer(_, __, message):
        if syslog:
            return 'feedhq[{}]: {}'.format(pid, message)
        return message
    return renderer


def root(lvl):
    return {'handlers': ['root'],
            'level': lvl,
            'propagate': False}


def configure_logging(debug=False, syslog=False, silenced_loggers=None,
                      level_overrides=None):
    if silenced_loggers is None:
        silenced_loggers = []
    if level_overrides is None:
        level_overrides = {}
    level = 'DEBUG' if debug else 'INFO'
    renderers = [
        dev.ConsoleRenderer(),
    ] if debug else [
        logstash_processor,
        processors.JSONRenderer(separators=(',', ':')),
        add_syslog_program(syslog),
    ]
    structlog_processors = [
        stdlib.filter_by_level,
        stdlib.add_logger_name,
        stdlib.add_log_level,
        fix_logger_name,
        format_request,
        ensure_event,
        stdlib.PositionalArgumentsFormatter(),
        processors.TimeStamper(fmt="ISO", key='@timestamp'),
        processors.StackInfoRenderer(),
        processors.format_exc_info,
    ] + renderers

    configure(
        processors=structlog_processors,
        context_class=dict,
        logger_factory=stdlib.LoggerFactory(),
        wrapper_class=stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    structlog = {'handlers': ['raw'],
                 'level': level,
                 'propagate': False}
    null = {'handlers': ['null'],
            'propagate': False}
    loggers = {l: root(level_overrides.get(l, level))
               for l, _, _ in logging_tree.tree()[2]}
    loggers['feedhq'] = structlog

    for nulled_logger in silenced_loggers:
        loggers[nulled_logger] = null

    raw = {
        'level': level,
        'class': 'logging.handlers.SysLogHandler',
        'address': '/dev/log',
        'facility': 'local0',
    } if syslog else {
        'level': level,
        'class': 'logging.StreamHandler',
    }

    return {
        'version': 1,
        'level': level,
        'handlers': {
            'root': {
                'level': level,
                '()': StructlogHandler,
            },
            'raw': raw,
            'null': {
                'class': 'logging.NullHandler',
            },
        },
        'loggers': loggers,
        'root': root(level),
    }
