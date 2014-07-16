Terminology
===========

Before building things with the API, it's important to understand a couple of
concepts that determine how the API works. The API is not particularly
resource-oriented, not so *RESTful*, but once the concepts are understood it's
rather easy to get data out of this API.

Data model
----------

The root element is a *feed*. It's simply the URL of an RSS feed that gets
polled for fetching feed items.

Feeds can optionally belong to a *label*. Google reader supported multiple
labels per feed but FeedHQ only allows feeds to belong to one (or zero) label.

Feed items — or just *items* — are articles, news items or posts that are
extracted and stored during feed fetching.

Streams
-------

*Streams* are lists of feed items. They represent a criteria that is used to
fetch a list of items, e.g.:

* the feed to which items belong to

* the label to which items belong to

* the state that items must have (starred, read)

Streams have an identifier called a *Stream ID*. This identifier can take
several forms:

* For a label, the string ``user/-/label/<name>`` where ``<name>`` is the
  label's name

* For a feed, the string ``feed/<feed url>`` where ``<feed url>`` is the
  complete URL for the feed

* For a state, the string ``user/-/state/com.google/<state>`` where
  ``<state>`` is one of ``read``, ``kept-unread``, ``broadcast``,
  ``broadcast-friends``, ``reading-list``, ``starred``, or any other string
  that gets interpreted as a *tag*.

* For a combination of multiple streams, the string ``splice/`` followed by
  stream IDs separated with the pipe (``|``) character. Splice items are
  combined in an OR query. E.g.
  ``splice/user/-/label/foo|user/-/state/com.google/starred`` represents all
  items that are starred **or** in the ``foo`` label.

Furthermore, for states or labels, the ``user/-/`` prefix can also contain the
user ID instead of the dash. ``user/12345/label/test`` is a valid stream ID,
assuming the number ``12345`` matches with the authenticated user making the
request.

Here is a summary of the filtering that is done for all states:

============================ ===============
State                        Filter
============================ ===============
read                         read items
kept-unread                  unread items
broadcast, broadcast-friends broadcast items
reading-list                 all items
starred                      starred items
============================ ===============

*broadcast* is more or less a no-op: FeedHQ stores this attribute and lets you
set it but there is no public-facing feature that uses this attribute yet.

All states that are not in this table are treated as *tags*. Items can be
tagged and searching for ``user/-/state/com.google/test`` will look for items
having the ``test`` tag.

Items
-----

Items are identified by a globally unique numerical *ID*. Item IDs can take
two forms:

* The short form, just the actual ID. E.g. ``12345``.

* The long form, the prefix ``tag:google.com,2005:reader/item/`` followed by
  the item ID as an unsigned base 16 number and 0-padded to be always 16
  characters long.

Examples:

================== =========
Short form         Long form
================== =========
``12309438943892`` ``tag:google.com,2005:reader/item/00000b3203bc5294``
``87238913628312`` ``tag:google.com,2005:reader/item/00004f57e4751898``
================== =========

Here is some sample Python code that converts from and to long-form IDs.

.. code-block:: python

    import struct

    def to_long_form(short_form):
        value = hex(struct.unpack("L", struct.pack("l", short_form))[0])
        if value.endswith("L"):
            value = value[:-]
        return 'tag:google.com,2005:reader/item/{0}'.format(
            value[2:].zfill(16)
        )

    def to_short_form(long_form):
        value = int(long_form.split('/')[-1], 16)
        return struct.unpack("l", struct.pack("L", value))[0]

When the API documentation mentions passing an *item ID* as a parameter,
clients are free to use the short form or the long form.

Input formats
-------------

API calls use the ``GET`` or ``POST`` HTTP methods. Some calls support both
methods, some don't.

When using ``GET``, parameters can be passed as querystring parameters.

When using ``POST``, parameters can be passed in the request body, as form
data with the ``application/x-www-form-urlencoded`` encoding.

In some cases parameters can be repeated, to treat them as lists. The API
simply expects parameters to be repeated. E.g. ``?i=12345&i=67890&i=…``.
*When the API expects a list*, it will understand that as
``i = [12345, 67890]``.

Authentication
--------------

API calls are authenticated using API tokens. The API call to retrieve a token
is ``/accounts/ClientLogin``.

This API call accepts both ``GET`` parameters and ``POST`` data, but it is
strongly recommended to use ``POST``.

URL: ``/accounts/ClientLogin``

Parameters:

* ``Email``: the user's email
* ``Passwd``: the user's account password

The response comes back as ``plain/text`` and contains 3 lines::

    SID=...
    LSID=...
    Auth=<token>

Clients should store the token from the third line, following the ``Auth=``
marker.

API tokens expire like web sessions. Clients need to renew them every now and
then. FeedHQ's expiration time for auth tokens is 7 days. When a token
expires, the API returns HTTP 401 responses.

Once a token has been generated, it needs to be passed in the HTTP
``Authorization`` header when making API calls, with the following format::

    Authorization: GoogleLogin auth=<token>

Output formats
--------------

The API supports content negotiation for most API calls. The commonly
supported formats are:

* XML
* JSON

Additionally, some API calls support Atom. Some only support one output format
and will disregard any content negotiation. Some other calls return plain text
responses when the data to return is simple enough.

Content negotiation can be done in two ways:

* with the HTTP ``Accept`` header
* with the ``output`` querystring parameter

Here are the relevant parameters to pass to the API

====== ================ ====================
Format Accept header    ``output`` parameter
====== ================ ====================
XML    application/xml  xml
JSON   application/json json
Atom   text/xml         atom
====== ================ ====================

The default output format — when nothing is specified by the client — is XML.

POST Token
----------

Additionally to authentication, API calls that mutate data in the FeedHQ
data store and that are made using the ``POST`` method need to include a *POST
token*.

The POST token is a short-lived token that is used for CSRF protection. It
must be included in request bodies as a ``T`` parameter.

Retrieving a POST token is as simple as issuing a GET request to
``/reader/api/0/token``. The token is returned as a plain-text string and can
be used in POST requests.

When the token is required but missing, the API will return an HTTP 400
response.

When the token is present but invalid, the API will return an HTTP 401
response with a special header, ``X-Reader-Google-Bad-Token: true``. This
header means that the token needs to be renewed by simply making a new request
to ``/reader/api/0/token`` and storing the updated token.

API Clients should use their tokens as long as they are valid, and renew them
only when they see the bad-token response.

FeedHQ's POST tokens are valid for 30 minutes.
