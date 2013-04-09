import os

from io import StringIO

from requests import Response as _Response


TEST_DATA = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')


def test_file(name):
    return os.path.join(TEST_DATA, name)


def responses(code, path=None, redirection=None,
              headers={'Content-Type': 'text/xml'}):
    response = _Response()
    response.status_code = code
    if path is not None:
        with open(test_file(path), 'r') as f:
            response.raw = StringIO(f.read().decode('utf-8'))
    if redirection is not None:
        temp = _Response()
        temp.status_code = 301 if 'permanent' in redirection else 302
        temp.url = path
        response.history.append(temp)
        response.url = redirection
    response.headers = headers
    return response
