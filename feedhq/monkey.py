import feedparser
from html5lib.filters import alphabeticalattributes


def key(item):
    (value, attr), *_ = item
    if value is None:
        value = ""
    return value, attr


class Filter(alphabeticalattributes.Filter):
    def __iter__(self):
        for token in alphabeticalattributes._base.Filter.__iter__(self):
            if token["type"] in {'StartTag', 'EmptyTag'}:
                attrs = alphabeticalattributes.OrderedDict()
                for name, value in sorted(token["data"].items(), key=key):
                    attrs[name] = value
                token["data"] = attrs
            yield token


def patch_html5lib():
    alphabeticalattributes.Filter = Filter


def _isBase64(self, attrsD, contentparams):
    if attrsD.get('mode', '') == 'base64':
        return 1
    if self.contentparams['type'].startswith('text/'):
        return 0
    if self.contentparams['type'].endswith('+xml'):
        return 0
    if self.contentparams['type'].endswith('/xml'):
        return 0
    if self.contentparams['type'] == 'markdown':
        return 0
    return 1


def patch_feedparser():
    feedparser._FeedParserMixin._isBase64 = _isBase64
