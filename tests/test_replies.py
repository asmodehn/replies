# coding: utf-8

import re
import asks
import replies
import pytest
from replies import BaseReply, Reply

from inspect import getargspec
from asks.errors import ConnectivityError, BadHttpResponse


def assert_reset():
    assert len(replies._default_mock._matches) == 0
    assert len(replies.calls) == 0


def assert_response(resp, body=None, content_type="text/plain"):
    assert resp.status_code == 200
    assert resp.reason == "OK"
    if content_type is not None:
        assert resp.headers["Content-Type"] == content_type
    else:
        assert "Content-Type" not in resp.headers
    assert resp.text == body


@pytest.mark.asyncio
async def test_response(asynclib):
    @replies.activate
    async def run():
        replies.add(replies.GET, "http://example.com", body=b"test")
        resp = await asks.get("http://example.com")
        assert_response(resp, "test")
        assert len(replies.calls) == 1
        assert replies.calls[0].request.url == "http://example.com/"
        assert replies.calls[0].response.content == b"test"

        resp = await asks.get("http://example.com?foo=bar")
        assert_response(resp, "test")
        assert len(replies.calls) == 2
        assert replies.calls[1].request.url == "http://example.com/?foo=bar"
        assert replies.calls[1].response.content == b"test"

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_response_with_instance(asynclib):
    @replies.activate
    async def run():
        replies.add(
            replies.Response(method=replies.GET, url="http://example.com")
        )
        resp = await asks.get("http://example.com")
        assert_response(resp, "")
        assert len(replies.calls) == 1
        assert replies.calls[0].request.url == "http://example.com/"

        resp = await asks.get("http://example.com?foo=bar")
        assert_response(resp, "")
        assert len(replies.calls) == 2
        assert replies.calls[1].request.url == "http://example.com/?foo=bar"


@pytest.mark.parametrize(
    "original,replacement",
    [
        ("http://example.com/two", "http://example.com/two"),
        (
            Reply(method=replies.GET, url="http://example.com/two"),
            Reply(
                method=replies.GET, url="http://example.com/two", body="testtwo"
            ),
        ),
        (
            re.compile(r"http://example\.com/two"),
            re.compile(r"http://example\.com/two"),
        ),
    ],
)
def test_replace(original, replacement):
    @replies.activate
    def run():
        replies.add(replies.GET, "http://example.com/one", body="test1")

        if isinstance(original, BaseReply):
            replies.add(original)
        else:
            replies.add(replies.GET, original, body="test2")

        replies.add(replies.GET, "http://example.com/three", body="test3")
        replies.add(
            replies.GET, re.compile(r"http://example\.com/four"), body="test3"
        )

        if isinstance(replacement, BaseReply):
            replies.replace(replacement)
        else:
            replies.replace(replies.GET, replacement, body="testtwo")

        resp = replies.get("http://example.com/two")
        assert_response(resp, "testtwo")

    run()
    assert_reset()


@pytest.mark.parametrize(
    "original,replacement",
    [
        ("http://example.com/one", re.compile(r"http://example\.com/one")),
        (re.compile(r"http://example\.com/one"), "http://example.com/one"),
    ],
)
def test_replace_error(original, replacement):
    @replies.activate
    def run():
        replies.add(replies.GET, original)
        with pytest.raises(ValueError):
            replies.replace(replies.GET, replacement)

    run()
    assert_reset()


@pytest.mark.asyncio
async def test_remove(asynclib):
    @replies.activate
    async def run():
        replies.add(replies.GET, "http://example.com/zero")
        replies.add(replies.GET, "http://example.com/one")
        replies.add(replies.GET, "http://example.com/two")
        replies.add(replies.GET, re.compile(r"http://example\.com/three"))
        replies.add(replies.GET, re.compile(r"http://example\.com/four"))
        re.purge()
        replies.remove(replies.GET, "http://example.com/two")
        replies.remove(Reply(method=replies.GET, url="http://example.com/zero"))
        replies.remove(replies.GET, re.compile(r"http://example\.com/four"))

        with pytest.raises(ConnectionError):
            await asks.get("http://example.com/zero")
        asks.get("http://example.com/one")
        with pytest.raises(ConnectionError):
            await asks.get("http://example.com/two")
        asks.get("http://example.com/three")
        with pytest.raises(ConnectionError):
            await asks.get("http://example.com/four")

    await run()
    assert_reset()


@pytest.mark.parametrize(
    "args1,kwargs1,args2,kwargs2,expected",
    [
        ((replies.GET, "a"), {}, (replies.GET, "a"), {}, True),
        ((replies.GET, "a"), {}, (replies.GET, "b"), {}, False),
        ((replies.GET, "a"), {}, (replies.POST, "a"), {}, False),
        (
            (replies.GET, "a"),
            {"match_querystring": True},
            (replies.GET, "a"),
            {},
            True,
        ),
    ],
)
def test_response_equality(args1, kwargs1, args2, kwargs2, expected):
    o1 = BaseReply(*args1, **kwargs1)
    o2 = BaseReply(*args2, **kwargs2)
    assert (o1 == o2) is expected
    assert (o1 != o2) is not expected


def test_response_equality_different_objects():
    o1 = BaseReply(method=replies.GET, url="a")
    o2 = "str"
    assert (o1 == o2) is False
    assert (o1 != o2) is True


@pytest.mark.asyncio
async def test_connection_error(asynclib):
    @replies.activate
    async def run():
        replies.add(replies.GET, "http://example.com")

        with pytest.raises(ConnectionError):
            await asks.get("http://example.com/foo")

        assert len(replies.calls) == 1
        assert replies.calls[0].request.url == "http://example.com/foo"
        assert type(replies.calls[0].response) is ConnectionError
        assert replies.calls[0].response.request

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_match_querystring(asynclib):
    @replies.activate
    async def run():
        url = "http://example.com?test=1&foo=bar"
        replies.add(replies.GET, url, match_querystring=True, body=b"test")
        resp = await asks.get("http://example.com?test=1&foo=bar")
        assert_response(resp, "test")
        resp = await asks.get("http://example.com?foo=bar&test=1")
        assert_response(resp, "test")
        resp = await asks.get("http://example.com/?foo=bar&test=1")
        assert_response(resp, "test")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_match_empty_querystring(asynclib):
    @replies.activate
    async def run():
        replies.add(
            replies.GET, "http://example.com", body=b"test", match_querystring=True
        )
        resp = await asks.get("http://example.com")
        assert_response(resp, "test")
        resp = await asks.get("http://example.com/")
        assert_response(resp, "test")
        with pytest.raises(ConnectionError):
            asks.get("http://example.com?query=foo")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_match_querystring_error(asynclib):
    @replies.activate
    async def run():
        replies.add(
            replies.GET, "http://example.com/?test=1", match_querystring=True
        )

        with pytest.raises(ConnectionError):
            await asks.get("http://example.com/foo/?test=2")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_match_querystring_regex(asynclib):
    @replies.activate
    async def run():
        """Note that `match_querystring` value shouldn't matter when passing a
        regular expression"""

        replies.add(
            replies.GET,
            re.compile(r"http://example\.com/foo/\?test=1"),
            body="test1",
            match_querystring=True,
        )

        resp = await asks.get("http://example.com/foo/?test=1")
        assert_response(resp, "test1")

        replies.add(
            replies.GET,
            re.compile(r"http://example\.com/foo/\?test=2"),
            body="test2",
            match_querystring=False,
        )

        resp = await asks.get("http://example.com/foo/?test=2")
        assert_response(resp, "test2")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_match_querystring_error_regex(asynclib):
    @replies.activate
    async def run():
        """Note that `match_querystring` value shouldn't matter when passing a
        regular expression"""

        replies.add(
            replies.GET,
            re.compile(r"http://example\.com/foo/\?test=1"),
            match_querystring=True,
        )

        with pytest.raises(ConnectionError):
            await asks.get("http://example.com/foo/?test=3")

        replies.add(
            replies.GET,
            re.compile(r"http://example\.com/foo/\?test=2"),
            match_querystring=False,
        )

        with pytest.raises(ConnectionError):
            await asks.get("http://example.com/foo/?test=4")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_accept_string_body(asynclib):
    @replies.activate
    async def run():
        url = "http://example.com/"
        replies.add(replies.GET, url, body="test")
        resp = await asks.get(url)
        assert_response(resp, "test")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_accept_json_body(asynclib):
    @replies.activate
    async def run():
        content_type = "application/json"

        url = "http://example.com/"
        replies.add(replies.GET, url, json={"message": "success"})
        resp = await asks.get(url)
        assert_response(resp, '{"message": "success"}', content_type)

        url = "http://example.com/1/"
        replies.add(replies.GET, url, json=[])
        resp = await asks.get(url)
        assert_response(resp, "[]", content_type)

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_no_content_type(asynclib):
    @replies.activate
    async def run():
        url = "http://example.com/"
        replies.add(replies.GET, url, body="test", content_type=None)
        resp = await asks.get(url)
        assert_response(resp, "test", content_type=None)

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_arbitrary_status_code(asynclib):
    @replies.activate
    async def run():
        url = "http://example.com/"
        replies.add(replies.GET, url, body="test", status=418)
        resp = await asks.get(url)
        assert resp.status_code == 418
        assert resp.reason is None

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_throw_connection_error_explicit(asynclib):
    @replies.activate
    async def run():
        url = "http://example.com"
        exception = HTTPError("HTTP Error")
        replies.add(replies.GET, url, exception)

        with pytest.raises(HTTPError) as HE:
            await asks.get(url)

        assert str(HE.value) == "HTTP Error"

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_callback(asynclib):
    body = b"test callback"
    status = 400
    reason = "Bad Request"
    headers = {"foo": "bar"}
    url = "http://example.com/"

    def request_callback(request):
        return (status, headers, body)

    @replies.activate
    async def run():
        replies.add_callback(replies.GET, url, request_callback)
        resp = await asks.get(url)
        assert resp.text == "test callback"
        assert resp.status_code == status
        assert resp.reason == reason
        assert "foo" in resp.headers
        assert resp.headers["foo"] == "bar"

    await run()
    assert_reset()


def test_callback_no_content_type():
    body = b"test callback"
    status = 400
    reason = "Bad Request"
    headers = {"foo": "bar"}
    url = "http://example.com/"

    def request_callback(request):
        return (status, headers, body)

    @replies.activate
    def run():
        replies.add_callback(replies.GET, url, request_callback, content_type=None)
        resp = asks.get(url)
        assert resp.text == "test callback"
        assert resp.status_code == status
        assert resp.reason == reason
        assert "foo" in resp.headers
        assert "Content-Type" not in resp.headers

    run()
    assert_reset()


def test_regular_expression_url():
    @replies.activate
    def run():
        url = re.compile(r"https?://(.*\.)?example.com")
        replies.add(replies.GET, url, body=b"test")

        resp = asks.get("http://example.com")
        assert_response(resp, "test")

        resp = asks.get("https://example.com")
        assert_response(resp, "test")

        resp = asks.get("https://uk.example.com")
        assert_response(resp, "test")

        with pytest.raises(ConnectionError):
            asks.get("https://uk.exaaample.com")

    run()
    assert_reset()


def test_custom_adapter():
    @replies.activate
    def run():
        url = "http://example.com"
        replies.add(replies.GET, url, body=b"test")

        calls = [0]

        class DummyAdapter(asks.adapters.HTTPAdapter):
            def send(self, *a, **k):
                calls[0] += 1
                return super(DummyAdapter, self).send(*a, **k)

        # Test that the adapter is actually used
        session = asks.Session()
        session.mount("http://", DummyAdapter())

        resp = session.get(url, allow_redirects=False)
        assert calls[0] == 1

        # Test that the response is still correctly emulated
        session = asks.Session()
        session.mount("http://", DummyAdapter())

        resp = session.get(url)
        assert_response(resp, "test")

    run()

@pytest.mark.asyncio
async def test_replies_as_context_manager():
    async def run():
        with replies.mock:
            replies.add(replies.GET, "http://example.com", body=b"test")
            resp = await asks.get("http://example.com")
            assert_response(resp, "test")
            assert len(replies.calls) == 1
            assert replies.calls[0].request.url == "http://example.com/"
            assert replies.calls[0].response.content == b"test"

            resp = asks.get("http://example.com?foo=bar")
            assert_response(resp, "test")
            assert len(replies.calls) == 2
            assert replies.calls[1].request.url == "http://example.com/?foo=bar"
            assert replies.calls[1].response.content == b"test"

    await run()
    assert_reset()


def test_activate_doesnt_change_signature():
    def test_function(a, b=None):
        return (a, b)

    decorated_test_function = replies.activate(test_function)
    assert getargspec(test_function) == getargspec(decorated_test_function)
    assert decorated_test_function(1, 2) == test_function(1, 2)
    assert decorated_test_function(3) == test_function(3)


def test_activate_doesnt_change_signature_for_method():
    class TestCase(object):
        def test_function(self, a, b=None):
            return (self, a, b)

    test_case = TestCase()
    argspec = getargspec(test_case.test_function)
    decorated_test_function = replies.activate(test_case.test_function)
    assert argspec == getargspec(decorated_test_function)
    assert decorated_test_function(1, 2) == test_case.test_function(1, 2)
    assert decorated_test_function(3) == test_case.test_function(3)


@pytest.mark.asyncio
async def test_response_cookies():
    body = b"test callback"
    status = 200
    headers = {"set-cookie": "session_id=12345; a=b; c=d"}
    url = "http://example.com/"

    def request_callback(request):
        return (status, headers, body)

    @replies.activate
    async def run():
        replies.add_callback(replies.GET, url, request_callback)
        resp = await asks.get(url)
        assert resp.text == "test callback"
        assert resp.status_code == status
        assert "session_id" in resp.cookies
        assert resp.cookies["session_id"] == "12345"
        assert resp.cookies["a"] == "b"
        assert resp.cookies["c"] == "d"

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_response_callback():
    """adds a callback to decorate the response, then checks it"""

    async def run():
        def response_callback(resp):
            resp._is_mocked = True
            return resp

        with replies.asksMock(response_callback=response_callback) as m:
            m.add(replies.GET, "http://example.com", body=b"test")
            resp = await asks.get("http://example.com")
            assert resp.text == "test"
            assert hasattr(resp, "_is_mocked")
            assert resp._is_mocked is True

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_response_filebody():
    """ Adds the possibility to use actual (binary) files as replies """

    async def run():
        with replies.RequestsMock() as m:
            with open("README.rst", "rb") as out:
                m.add(replies.GET, "http://example.com", body=out, stream=True)
                resp = await asks.get("http://example.com")
            with open("README.rst", "r") as out:
                assert resp.text == out.read()

    #await run()
    #assert_reset()


@pytest.mark.asyncio
async def test_assert_all_asks_are_fired():
    async def run():
        with pytest.raises(AssertionError) as excinfo:
            with replies.AsksMock(assert_all_asks_are_fired=True) as m:
                m.add(replies.GET, "http://example.com", body=b"test")
        assert "http://example.com" in str(excinfo.value)
        assert replies.GET in str(excinfo)

        # check that assert_all_asks_are_fired default to True
        with pytest.raises(AssertionError):
            with replies.AsksMock() as m:
                m.add(replies.GET, "http://example.com", body=b"test")

        # check that assert_all_asks_are_fired doesn't swallow exceptions
        with pytest.raises(ValueError):
            with replies.AsksMock() as m:
                m.add(replies.GET, "http://example.com", body=b"test")
                raise ValueError()

        # check that assert_all_asks_are_fired=True doesn't remove urls
        with replies.AsksMock(assert_all_asks_are_fired=True) as m:
            m.add(replies.GET, "http://example.com", body=b"test")
            assert len(m._matches) == 1
            await asks.get("http://example.com")
            assert len(m._matches) == 1

        # check that assert_all_asks_are_fired=True counts mocked errors
        with replies.AsksMock(assert_all_asks_are_fired=True) as m:
            m.add(replies.GET, "http://example.com", body=Exception())
            assert len(m._matches) == 1
            with pytest.raises(Exception):
                await asks.get("http://example.com")
            assert len(m._matches) == 1

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_allow_redirects_samehost():
    redirecting_url = "http://example.com"
    final_url_path = "/1"
    final_url = "{0}{1}".format(redirecting_url, final_url_path)
    url_re = re.compile(r"^http://example.com(/)?(\d+)?$")

    def request_callback(request):
        # endpoint of chained redirect
        if request.url.endswith(final_url_path):
            return 200, (), b"test"

        # otherwise redirect to an integer path
        else:
            if request.url.endswith("/0"):
                n = 1
            else:
                n = 0
            redirect_headers = {"location": "/{0!s}".format(n)}
            return 301, redirect_headers, None

    async def run():
        # setup redirect
        with replies.mock:
            replies.add_callback(replies.GET, url_re, request_callback)
            resp_no_redirects = await asks.get(redirecting_url, allow_redirects=False)
            assert resp_no_redirects.status_code == 301
            assert len(replies.calls) == 1  # 1x300
            assert replies.calls[0][1].status_code == 301
        assert_reset()

        with replies.mock:
            replies.add_callback(replies.GET, url_re, request_callback)
            resp_yes_redirects = await asks.get(redirecting_url, allow_redirects=True)
            assert len(replies.calls) == 3  # 2x300 + 1x200
            assert len(resp_yes_redirects.history) == 2
            assert resp_yes_redirects.status_code == 200
            assert final_url == resp_yes_redirects.url
            status_codes = [call[1].status_code for call in replies.calls]
            assert status_codes == [301, 301, 200]
        assert_reset()

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_handles_unicode_querystring():
    url = "http://example.com/test?type=2&ie=utf8&query=汉字"

    @replies.activate
    async def run():
        replies.add(replies.GET, url, body="test", match_querystring=True)

        resp = await asks.get(url)

        assert_response(resp, "test")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_handles_unicode_url():
    url = "http://www.संजाल.भारत/hi/वेबसाइट-डिजाइन"

    @replies.activate
    async def run():
        replies.add(replies.GET, url, body="test")

        resp = await asks.get(url)

        assert_response(resp, "test")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_headers():
    @replies.activate
    async def run():
        replies.add(
            replies.GET, "http://example.com", body="", headers={"X-Test": "foo"}
        )
        resp = await asks.get("http://example.com")
        assert resp.headers["X-Test"] == "foo"

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_legacy_adding_headers(asynclib):
    @replies.activate
    async def run():
        replies.add(
            replies.GET,
            "http://example.com",
            body="",
            adding_headers={"X-Test": "foo"},
        )
        resp = await asks.get("http://example.com")
        assert resp.headers["X-Test"] == "foo"

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_multiple_replies(asynclib):
    @replies.activate
    async def run():
        replies.add(replies.GET, "http://example.com", body="test")
        replies.add(replies.GET, "http://example.com", body="rest")

        resp = await asks.get("http://example.com")
        assert_response(resp, "test")
        resp = await asks.get("http://example.com")
        assert_response(resp, "rest")
        # After all replies are used, last response should be repeated
        resp = await asks.get("http://example.com")
        assert_response(resp, "rest")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_multiple_urls(asynclib):
    @replies.activate
    async def run():
        replies.add(replies.GET, "http://example.com/one", body="one")
        replies.add(replies.GET, "http://example.com/two", body="two")

        resp = await asks.get("http://example.com/two")
        assert_response(resp, "two")
        resp = await asks.get("http://example.com/one")
        assert_response(resp, "one")

    await run()
    assert_reset()

@pytest.mark.asyncio
async def test_passthru(asynclib, httpserver):
    httpserver.serve_content("OK", headers={"Content-Type": "text/plain"})

    @replies.activate
    async def run():
        replies.add_passthru(httpserver.url)
        replies.add(replies.GET, "{}/one".format(httpserver.url), body="one")
        replies.add(replies.GET, "http://example.com/two", body="two")

        resp = await asks.get("http://example.com/two")
        assert_response(resp, "two")
        resp = await asks.get("{}/one".format(httpserver.url))
        assert_response(resp, "one")
        resp = await asks.get(httpserver.url)
        assert_response(resp, "OK")

    await run()
    assert_reset()


@pytest.mark.asyncio
async def test_method_named_param(asynclib):
    @replies.activate
    async def run():
        replies.add(method=replies.GET, url="http://example.com", body="OK")
        resp = await asks.get("http://example.com")
        assert_response(resp, "OK")

    await run()
    assert_reset()


def test_passthru_unicode():
    @replies.activate
    def run():
        with replies.AsksMock() as m:
            url = "http://موقع.وزارة-الاتصالات.مصر/"
            clean_url = "http://xn--4gbrim.xn----ymcbaaajlc6dj7bxne2c.xn--wgbh1c/"
            m.add_passthru(url)
            assert m.passthru_prefixes[0] == clean_url

    run()
    assert_reset()


def test_custom_target(monkeypatch):
    asks_mock = replies.AsksMock(target="something.else")
    std_mock_mock = replies.std_mock.MagicMock()
    patch_mock = std_mock_mock.patch
    monkeypatch.setattr(replies, "std_mock", std_mock_mock)
    asks_mock.start()
    assert len(patch_mock.call_args_list) == 1
    assert patch_mock.call_args[1]["target"] == "something.else"


if __name__ == '__main__':
    pytest.main(['-s', __file__])
