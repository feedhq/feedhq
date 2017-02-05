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
