import json as json_module
import re
import six

try:
    from requests.packages.urllib3.response import HTTPResponse
except ImportError:
    from urllib3.response import HTTPResponse

from urllib.parse import urlparse, parse_qsl

try:
    from unittest import mock as std_mock
except ImportError:
    import mock as std_mock

try:
    Pattern = re._pattern_type
except AttributeError:
    # Python 3.7
    Pattern = re.Pattern


from ._utils import _ensure_url_default_path, _is_string, _has_unicode, _clean_unicode, _handle_body


UNSET = object()


class BaseReply(object):
    content_type = None
    headers = None

    stream = False

    def __init__(self, method, url, match_querystring=False):
        self.method = method
        self.match_querystring = match_querystring
        # ensure the url has a default path set if the url is a string
        self.url = _ensure_url_default_path(url)
        self.call_count = 0

    def __eq__(self, other):
        if not isinstance(other, BaseReply):
            return False

        if self.method != other.method:
            return False

        # Can't simply do a equality check on the objects directly here since __eq__ isn't
        # implemented for regex. It might seem to work as regex is using a cache to return
        # the same regex instances, but it doesn't in all cases.
        self_url = self.url.pattern if isinstance(self.url, Pattern) else self.url
        other_url = other.url.pattern if isinstance(other.url, Pattern) else other.url

        return self_url == other_url

    def __ne__(self, other):
        return not self.__eq__(other)

    def _url_matches_strict(self, url, other):
        url_parsed = urlparse(url)
        other_parsed = urlparse(other)

        if url_parsed[:3] != other_parsed[:3]:
            return False

        url_qsl = sorted(parse_qsl(url_parsed.query))
        other_qsl = sorted(parse_qsl(other_parsed.query))

        if len(url_qsl) != len(other_qsl):
            return False

        for (a_k, a_v), (b_k, b_v) in zip(url_qsl, other_qsl):
            if a_k != b_k:
                return False

            if a_v != b_v:
                return False

        return True

    def _url_matches(self, url, other, match_querystring=False):
        if _is_string(url):
            if _has_unicode(url):
                url = _clean_unicode(url)
                if not isinstance(other, six.text_type):
                    other = other.encode("ascii").decode("utf8")
            if match_querystring:
                return self._url_matches_strict(url, other)

            else:
                url_without_qs = url.split("?", 1)[0]
                other_without_qs = other.split("?", 1)[0]
                return url_without_qs == other_without_qs

        elif isinstance(url, Pattern) and url.match(other):
            return True

        else:
            return False

    def get_headers(self):
        headers = {}
        if self.content_type is not None:
            headers["Content-Type"] = self.content_type
        if self.headers:
            headers.update(self.headers)
        return headers

    def get_response(self, request):
        raise NotImplementedError

    def matches(self, request):
        if request.method != self.method:
            return False

        if not self._url_matches(self.url, request.url, self.match_querystring):
            return False

        return True


class Reply(BaseReply):
    def __init__(
        self,
        method,
        url,
        body="",
        json=None,
        status=200,
        headers=None,
        stream=False,
        content_type=UNSET,
        **kwargs
    ):
        # if we were passed a `json` argument,
        # override the body and content_type
        if json is not None:
            assert not body
            body = json_module.dumps(json)
            if content_type is UNSET:
                content_type = "application/json"

        if content_type is UNSET:
            content_type = "text/plain"

        # body must be bytes
        if isinstance(body, six.text_type):
            body = body.encode("utf-8")

        self.body = body
        self.status = status
        self.headers = headers
        self.stream = stream
        self.content_type = content_type
        super(Reply, self).__init__(method, url, **kwargs)

    def get_response(self, request):
        if self.body and isinstance(self.body, Exception):
            raise self.body

        headers = self.get_headers()
        status = self.status
        body = _handle_body(self.body)

        return HTTPResponse(
            status=status,
            reason=six.moves.http_client.responses.get(status),
            body=body,
            headers=headers,
            preload_content=False,
        )


class CallbackReply(BaseReply):
    def __init__(
        self, method, url, callback, stream=False, content_type="text/plain", **kwargs
    ):
        self.callback = callback
        self.stream = stream
        self.content_type = content_type
        super(CallbackReply, self).__init__(method, url, **kwargs)

    def get_response(self, request):
        headers = self.get_headers()

        result = self.callback(request)
        if isinstance(result, Exception):
            raise result

        status, r_headers, body = result
        body = _handle_body(body)
        headers.update(r_headers)

        return HTTPResponse(
            status=status,
            reason=six.moves.http_client.responses.get(status),
            body=body,
            headers=headers,
            preload_content=False,
        )
