import datetime

from django.utils.xmlutils import SimplerXMLGenerator
from rest_framework.compat import StringIO
from rest_framework.renderers import BaseRenderer, XMLRenderer


def timestamp_to_iso(value):
    return datetime.datetime.fromtimestamp(
        value).strftime("%Y-%m-%dT%H:%M:%SZ")


class PlainRenderer(BaseRenderer):
    media_type = 'text/plain'
    format = '*'

    def render(self, data, *args, **kwargs):
        if (isinstance(data, dict) and data.keys() == ['detail']):
            return data['detail']
        return data


class BaseXMLRenderer(XMLRenderer):
    strip_declaration = True

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return ''

        stream = StringIO()
        xml = SimplerXMLGenerator(stream, "utf-8")
        xml.startDocument()

        self._to_xml(xml, data)

        xml.endDocument()
        response = stream.getvalue()

        if self.strip_declaration:
            declaration = '<?xml version="1.0" encoding="utf-8"?>'
            if response.startswith(declaration):
                response = response[len(declaration):]
        return response.strip()


class GoogleReaderXMLRenderer(BaseXMLRenderer):
    def _to_xml(self, xml, data):
        """
        Renders *data* into serialized XML, google-reader style.
        """
        if isinstance(data, dict) and data:
            xml.startElement("object", {})
            for key, value in data.items():
                if isinstance(value, basestring) and value.isdigit():
                    value = int(value)
                if isinstance(value, (list, tuple)):
                    xml.startElement("list", {'name': key})
                    for item in value:
                        self._to_xml(xml, item)
                    xml.endElement("list")
                elif isinstance(value, int):
                    xml.startElement("number", {'name': key})
                    xml.characters(str(value))
                    xml.endElement("number")
                elif isinstance(value, basestring):
                    xml.startElement("string", {'name': key})
                    xml.characters(value)
                    xml.endElement("string")
                elif isinstance(value, dict):
                    xml.startElement("object", {'name': key})
                    self._to_xml(xml, value)
                    xml.endElement("object")
            xml.endElement("object")
        elif data == {}:
            pass
        elif isinstance(data, basestring):
            xml.startElement("string", {})
            xml.characters(data)
            xml.endElement("string")
        else:  # Unhandled case
            assert False, data


class AtomRenderer(BaseXMLRenderer):
    media_type = 'text/xml'
    format = 'atom'
    strip_declaration = False

    def _to_xml(self, xml, data):
        if data.keys() == ['detail']:
            xml.startElement('error', {})
            xml.characters(data['detail'])
            xml.endElement('error')
            return
        xml.startElement('feed', {
            'xmlns:media': 'http://search.yahoo.com/mrss/',
            'xmlns:gr': 'http://www.google.com/schemas/reader/atom/',
            'xmlns:idx': 'urn:atom-extension:indexing',
            'xmlns': 'http://www.w3.org/2005/Atom',
            'idx:index': 'no',
            'gr:dir': data['direction'],
        })

        xml.startElement('generator', {'uri': 'https://feedhq.org'})
        xml.characters('FeedHQ')
        xml.endElement('generator')

        xml.startElement('id', {})
        xml.characters(u'tag:google.com,2005:reader/{0}'.format(data['id']))
        xml.endElement('id')

        xml.startElement('title', {})
        xml.characters(data['title'])
        xml.endElement('title')

        if 'continuation' in data:
            xml.startElement('gr:continuation', {})
            xml.characters(data['continuation'])
            xml.endElement('gr:continuation')

        xml.startElement('link', {'rel': 'self',
                                  'href': data['self'][0]['href']})
        xml.endElement('link')

        if 'alternate' in data:
            xml.startElement('link', {'rel': 'alternate', 'type': 'text/html',
                                      'href': data['alternate'][0]['href']})
            xml.endElement('link')

        xml.startElement('updated', {})
        xml.characters(timestamp_to_iso(data['updated']))
        xml.endElement('updated')

        for entry in data['items']:
            xml.startElement('entry', {
                'gr:crawl-timestamp-msec': entry['crawlTimeMsec']})

            xml.startElement('id', {})
            xml.characters(entry['id'])
            xml.endElement('id')

            for category in entry['categories']:
                xml.startElement('category', {
                    'term': category,
                    'scheme': 'http://www.google.com/reader/',
                    'label': category.rsplit('/', 1)[1]})
                xml.endElement('category')

            xml.startElement('title', {'type': 'html'})
            xml.characters(entry['title'])
            xml.endElement('title')

            xml.startElement('published', {})
            xml.characters(timestamp_to_iso(entry['updated']))
            xml.endElement('published')

            xml.startElement('updated', {})
            xml.characters(timestamp_to_iso(entry['updated']))
            xml.endElement('updated')

            xml.startElement('link', {'rel': 'alternate', 'type': 'text/html',
                                      'href': entry['alternate'][0]['href']})
            xml.endElement('link')

            xml.startElement('content',
                             {'type': 'html',
                              'xml:base': entry['origin']['htmlUrl']})
            xml.characters(entry['content']['content'])
            xml.endElement('content')

            xml.startElement('author', {})
            xml.startElement('name', {})
            xml.characters(entry.get('author', data['author']))
            xml.endElement('name')
            xml.endElement('author')

            xml.startElement('source', {
                'gr:stream-id': entry['origin']['streamId']})

            xml.startElement('id', {})
            xml.characters(entry['id'])
            xml.endElement('id')

            xml.startElement('title', {'type': 'html'})
            xml.characters(entry['origin']['title'])
            xml.endElement('title')

            xml.startElement('link', {'rel': 'alternate',
                                      'type': 'text/html',
                                      'href': entry['origin']['htmlUrl']})
            xml.endElement('link')
            xml.endElement('source')

            xml.endElement('entry')

        xml.endElement('feed')


class AtomHifiRenderer(AtomRenderer):
    format = 'atom-hifi'
