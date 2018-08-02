import re
from cookies import Cookies

# from requests.exceptions import ConnectionError
# from requests.utils import cookiejar_from_dict

#try:
#    from requests.packages.urllib3.response import HTTPResponse
#except ImportError:
#    from urllib3.response import HTTPResponse


#from requests.adapters import HTTPAdapter
_real_send = HTTPAdapter.send

try:
    from unittest import mock as std_mock
except ImportError:
    import mock as std_mock

try:
    Pattern = re._pattern_type
except AttributeError:
    # Python 3.7
    Pattern = re.Pattern

from ._utils import CallList, _has_unicode, _clean_unicode, _wrapper_template, get_wrapped
from .reply import Reply, BaseReply, CallbackReply

import logging
logger = logging.getLogger("replies")


class AsksMock(object):
    DELETE = "DELETE"
    GET = "GET"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    PATCH = "PATCH"
    POST = "POST"
    PUT = "PUT"
    response_callback = None

    def __init__(
        self,
        assert_all_requests_are_fired=True,
        response_callback=None,
        passthru_prefixes=(),
        target="requests.adapters.HTTPAdapter.send",
    ):
        self._calls = CallList()
        self.reset()
        self.assert_all_requests_are_fired = assert_all_requests_are_fired
        self.response_callback = response_callback
        self.passthru_prefixes = tuple(passthru_prefixes)
        self.target = target

    def reset(self):
        self._matches = []
        self._calls.reset()

    def add(
        self,
        method=None,  # method or ``Response``
        url=None,
        body="",
        adding_headers=None,
        *args,
        **kwargs
    ):
        """
        A basic request:

        >>> replies.add(replies.GET, 'http://example.com')

        You can also directly pass an object which implements the
        ``BaseResponse`` interface:

        >>> replies.add(Response(...))

        A JSON payload:

        >>> replies.add(
        >>>     method='GET',
        >>>     url='http://example.com',
        >>>     json={'foo': 'bar'},
        >>> )

        Custom headers:

        >>> replies.add(
        >>>     method='GET',
        >>>     url='http://example.com',
        >>>     headers={'X-Header': 'foo'},
        >>> )


        Strict query string matching:

        >>> replies.add(
        >>>     method='GET',
        >>>     url='http://example.com?foo=bar',
        >>>     match_querystring=True
        >>> )
        """
        if isinstance(method, BaseReply):
            self._matches.append(method)
            return

        if adding_headers is not None:
            kwargs.setdefault("headers", adding_headers)

        self._matches.append(Reply(method=method, url=url, body=body, **kwargs))

    def add_passthru(self, prefix):
        """
        Register a URL prefix to passthru any non-matching mock requests to.

        For example, to allow any request to 'https://example.com', but require
        mocks for the remainder, you would add the prefix as so:

        >>> replies.add_passthru('https://example.com')
        """
        if _has_unicode(prefix):
            prefix = _clean_unicode(prefix)
        self.passthru_prefixes += (prefix,)

    def remove(self, method_or_response=None, url=None):
        """
        Removes a response previously added using ``add()``, identified
        either by a response object inheriting ``BaseResponse`` or
        ``method`` and ``url``. Removes all matching replies.

        >>> replies.add(replies.GET, 'http://example.org')
        >>> replies.remove(replies.GET, 'http://example.org')
        """
        if isinstance(method_or_response, BaseReply):
            response = method_or_response
        else:
            response = BaseReply(method=method_or_response, url=url)

        while response in self._matches:
            self._matches.remove(response)

    def replace(self, method_or_response=None, url=None, body="", *args, **kwargs):
        """
        Replaces a response previously added using ``add()``. The signature
        is identical to ``add()``. The response is identified using ``method``
        and ``url``, and the first matching response is replaced.

        >>> replies.add(replies.GET, 'http://example.org', json={'data': 1})
        >>> replies.replace(replies.GET, 'http://example.org', json={'data': 2})
        """
        if isinstance(method_or_response, BaseReply):
            response = method_or_response
        else:
            response = Reply(method=method_or_response, url=url, body=body, **kwargs)

        index = self._matches.index(response)
        self._matches[index] = response

    def add_callback(
        self, method, url, callback, match_querystring=False, content_type="text/plain"
    ):
        # ensure the url has a default path set if the url is a string
        # url = _ensure_url_default_path(url, match_querystring)

        self._matches.append(
            CallbackReply(
                url=url,
                method=method,
                callback=callback,
                content_type=content_type,
                match_querystring=match_querystring,
            )
        )

    @property
    def calls(self):
        return self._calls

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type, value, traceback):
        success = type is None
        self.stop(allow_assert=success)
        self.reset()
        return success

    def activate(self, func):
        evaldict = {"replies": self, "func": func}
        return get_wrapped(func, _wrapper_template, evaldict)

    def _find_match(self, request):
        found = None
        found_match = None
        for i, match in enumerate(self._matches):
            if match.matches(request):
                if found is None:
                    found = i
                    found_match = match
                else:
                    # Multiple matches found.  Remove & return the first match.
                    return self._matches.pop(found)

        return found_match

    def _on_request(self, adapter, request, **kwargs):
        match = self._find_match(request)
        resp_callback = self.response_callback

        if match is None:
            if request.url.startswith(self.passthru_prefixes):
                logger.info("request.allowed-passthru", extra={"url": request.url})
                return _real_send(adapter, request, **kwargs)

            error_msg = "Connection refused: {0} {1}".format(
                request.method, request.url
            )
            response = ConnectionError(error_msg)
            response.request = request

            self._calls.add(request, response)
            response = resp_callback(response) if resp_callback else response
            raise response

        try:
            response = adapter.build_response(request, match.get_response(request))
        except Exception as response:
            match.call_count += 1
            self._calls.add(request, response)
            response = resp_callback(response) if resp_callback else response
            raise

        if not match.stream:
            response.content  # NOQA

        try:
            resp_cookies = Cookies.from_request(response.headers["set-cookie"])
            response.cookies = cookiejar_from_dict(
                dict((v.name, v.value) for _, v in resp_cookies.items())
            )
        except (KeyError, TypeError):
            pass

        response = resp_callback(response) if resp_callback else response
        match.call_count += 1
        self._calls.add(request, response)
        return response

    def start(self):
        def unbound_on_send(adapter, request, *a, **kwargs):
            return self._on_request(adapter, request, *a, **kwargs)

        self._patcher = std_mock.patch(target=self.target, new=unbound_on_send)
        self._patcher.start()

    def stop(self, allow_assert=True):
        self._patcher.stop()
        if not self.assert_all_requests_are_fired:
            return

        if not allow_assert:
            return

        not_called = [m for m in self._matches if m.call_count == 0]
        if not_called:
            raise AssertionError(
                "Not all requests have been executed {0!r}".format(
                    [(match.method, match.url) for match in not_called]
                )
            )




#if __name__ == '__main__':
#    import doctest
#    doctest.testmod()
