import _io
import inspect
import logging
import re
import six

from collections import namedtuple, Sequence, Sized
from functools import update_wrapper

#from requests.sessions import REDIRECT_STATI

#try:
#    from requests.packages.urllib3.response import HTTPResponse
#except ImportError:
#    from urllib3.response import HTTPResponse

from urllib.parse import urlsplit, urlunsplit, quote

from io import BytesIO as BufferIO

try:
    from unittest import mock as std_mock
except ImportError:
    import mock as std_mock

try:
    Pattern = re._pattern_type
except AttributeError:
    # Python 3.7
    Pattern = re.Pattern


Call = namedtuple("Call", ["request", "response"])


_wrapper_template = """\
def wrapper%(signature)s:
    with replies:
        return func%(funcargs)s
"""




def _is_string(s):
    return isinstance(s, six.string_types)


def _has_unicode(s):
    return any(ord(char) > 128 for char in s)


def _clean_unicode(url):
    # Clean up domain names, which use punycode to handle unicode chars
    urllist = list(urlsplit(url))
    netloc = urllist[1]
    if _has_unicode(netloc):
        domains = netloc.split(".")
        for i, d in enumerate(domains):
            if _has_unicode(d):
                d = "xn--" + d.encode("punycode").decode("ascii")
                domains[i] = d
        urllist[1] = ".".join(domains)
        url = urlunsplit(urllist)

    # Clean up path/query/params, which use url-encoding to handle unicode chars
    if isinstance(url.encode("utf8"), six.string_types):
        url = url.encode("utf8")
    chars = list(url)
    for i, x in enumerate(chars):
        if ord(x) > 128:
            chars[i] = quote(x)

    return "".join(chars)


def _is_redirect(response):
    try:
        # 2.0.0 <= requests <= 2.2
        return response.is_redirect

    except AttributeError:
        # requests > 2.2
        return (
            # use request.sessions conditional
            response.status_code in REDIRECT_STATI
            and "location" in response.headers
        )


def get_wrapped(func, wrapper_template, evaldict):
    # Preserve the argspec for the wrapped function so that testing
    # tools such as pytest can continue to use their fixture injection.
    args, a, kw, defaults, kwonlyargs, kwonlydefaults, annotations = inspect.getfullargspec(
        func
    )

    signature = inspect.formatargspec(args, a, kw, defaults)
    is_bound_method = hasattr(func, "__self__")
    if is_bound_method:
        args = args[1:]  # Omit 'self'
    callargs = inspect.formatargspec(args, a, kw, None)

    ctx = {"signature": signature, "funcargs": callargs}
    six.exec_(wrapper_template % ctx, evaldict)

    wrapper = evaldict["wrapper"]

    update_wrapper(wrapper, func)
    if is_bound_method:
        wrapper = wrapper.__get__(func.__self__, type(func.__self__))
    return wrapper


class CallList(Sequence, Sized):
    def __init__(self):
        self._calls = []

    def __iter__(self):
        return iter(self._calls)

    def __len__(self):
        return len(self._calls)

    def __getitem__(self, idx):
        return self._calls[idx]

    def add(self, request, response):
        self._calls.append(Call(request, response))

    def reset(self):
        self._calls = []


def _ensure_url_default_path(url):
    if _is_string(url):
        url_parts = list(urlsplit(url))
        if url_parts[2] == "":
            url_parts[2] = "/"
        url = urlunsplit(url_parts)
    return url


def _handle_body(body):
    if isinstance(body, six.text_type):
        body = body.encode("utf-8")
    if isinstance(body, _io.BufferedReader):
        return body

    return BufferIO(body)

