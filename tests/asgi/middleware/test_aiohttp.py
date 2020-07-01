# Derived from https://github.com/aws/aws-xray-sdk-python/blob/master/tests/ext/aiohttp/test_middleware.py

"""Test the asyncio middleware with aiohttp server."""

import asyncio
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.web_exceptions import HTTPUnauthorized
from aws_xray_sdk import global_sdk_config
from aws_xray_sdk.core.async_context import AsyncContext
from aws_xray_sdk.core.emitters.udp_emitter import UDPEmitter
from aws_xray_sdk.core.models import http
from aws_xray_sdk.ext.aiohttp.middleware import middleware

from ...xray_util import get_new_stubbed_recorder

pytestmark = pytest.mark.asyncio


# Import just the client helper fixture from aiohttp, without polluting our
# fixture namespace with all the cray-cray in the `pytest-aiohttp` pytest
# plugin (like yet another `loop`).
#
# noinspection PyUnresolvedReferences
from aiohttp.pytest_plugin import aiohttp_client


# Inject a `loop` fixture based on the normal `event_loop` fixture,
# since aiohttp_client has this as a dependency
@pytest.fixture
async def loop(event_loop):
    yield event_loop


@pytest.fixture
async def client(event_loop, aiohttp_client):
    # Note that aiohttp is not actually ASGI-compliant, so we need to use
    # a custom client (not the usual `async_asgi_testclient.AsyncTestClient`)
    client = await aiohttp_client(ServerTest.app(loop=event_loop))
    yield client


class CustomStubbedEmitter(UDPEmitter):
    """
    Custom stubbed emitter which stores all segments instead of the last one
    """

    def __init__(self, daemon_address="127.0.0.1:2000"):
        super(CustomStubbedEmitter, self).__init__(daemon_address)
        self.local = []

    def send_entity(self, entity):
        self.local.append(entity)

    def pop(self):
        try:
            return self.local.pop(0)
        except IndexError:
            return None


class ServerTest(object):
    """
    Simple class to hold a copy of the event loop
    """

    __test__ = False

    def __init__(self, loop):
        self._loop = loop

    async def handle_ok(self, request: web.Request) -> web.Response:
        """
        Handle / request
        """
        if "content_length" in request.query:
            headers = {"Content-Length": request.query["content_length"]}
        else:
            headers = None

        return web.Response(text="ok", headers=headers)

    async def handle_error(self, request: web.Request) -> web.Response:
        """
        Handle /error which returns a 404
        """
        return web.Response(text="not found", status=404)

    async def handle_unauthorized(self, request: web.Request) -> web.Response:
        """
        Handle /unauthorized which returns a 401
        """
        raise HTTPUnauthorized()

    async def handle_exception(self, request: web.Request) -> web.Response:
        """
        Handle /exception which raises a KeyError
        """
        return {}["key"]

    async def handle_delay(self, request: web.Request) -> web.Response:
        """
        Handle /delay request
        """
        await asyncio.sleep(0.3, loop=self._loop)
        return web.Response(text="ok")

    def get_app(self) -> web.Application:
        app = web.Application(middlewares=[middleware])
        app.router.add_get("/", self.handle_ok)
        app.router.add_get("/error", self.handle_error)
        app.router.add_get("/exception", self.handle_exception)
        app.router.add_get("/unauthorized", self.handle_unauthorized)
        app.router.add_get("/delay", self.handle_delay)

        return app

    @classmethod
    def app(cls, loop=None) -> web.Application:
        return cls(loop=loop).get_app()


@pytest.fixture(scope="function")
def recorder(event_loop):
    """
    Clean up context storage before and after each test run
    """
    xray_recorder = get_new_stubbed_recorder()
    xray_recorder.configure(
        service="test", sampling=False, context=AsyncContext(loop=event_loop)
    )

    patcher = patch("aws_xray_sdk.ext.aiohttp.middleware.xray_recorder", xray_recorder)
    patcher.start()

    xray_recorder.clear_trace_entities()
    yield xray_recorder
    global_sdk_config.set_sdk_enabled(True)
    xray_recorder.clear_trace_entities()
    patcher.stop()


async def test_ok(client, recorder):
    """
    Test a normal response
    """
    resp = await client.get("/")
    assert resp.status == 200

    segment = recorder.emitter.pop()
    assert not segment.in_progress

    request = segment.http["request"]
    response = segment.http["response"]

    assert request["method"] == "GET"
    assert request["url"] == "http://127.0.0.1:{port}/".format(port=client.port)
    assert response["status"] == 200


async def test_ok_x_forwarded_for(client, recorder):
    """
    Test a normal response with x_forwarded_for headers
    """
    resp = await client.get("/", headers={"X-Forwarded-For": "foo"})
    assert resp.status == 200

    segment = recorder.emitter.pop()
    assert segment.http["request"]["client_ip"] == "foo"
    assert segment.http["request"]["x_forwarded_for"]


async def test_ok_content_length(client, recorder):
    """
    Test a normal response with content length as response header
    """
    resp = await client.get("/?content_length=100")
    assert resp.status == 200

    segment = recorder.emitter.pop()
    assert segment.http["response"]["content_length"] == 100


async def test_error(client, recorder):
    """
    Test a 4XX response
    """
    resp = await client.get("/error")
    assert resp.status == 404

    segment = recorder.emitter.pop()
    assert not segment.in_progress
    assert segment.error

    request = segment.http["request"]
    response = segment.http["response"]
    assert request["method"] == "GET"
    assert request["url"] == "http://127.0.0.1:{port}/error".format(port=client.port)
    assert request["client_ip"] == "127.0.0.1"
    assert response["status"] == 404


async def test_exception(client, recorder):
    """
    Test handling an exception
    """
    resp = await client.get("/exception")
    await resp.text()  # Need this to trigger Exception

    segment = recorder.emitter.pop()
    assert not segment.in_progress
    assert segment.fault

    request = segment.http["request"]
    response = segment.http["response"]
    exception = segment.cause["exceptions"][0]
    assert request["method"] == "GET"
    assert request["url"] == "http://127.0.0.1:{port}/exception".format(
        port=client.port
    )
    assert request["client_ip"] == "127.0.0.1"
    assert response["status"] == 500
    assert exception.type == "KeyError"


async def test_unhauthorized(client, recorder):
    """
    Test a 401 response
    """
    resp = await client.get("/unauthorized")
    assert resp.status == 401

    segment = recorder.emitter.pop()
    assert not segment.in_progress
    assert segment.error

    request = segment.http["request"]
    response = segment.http["response"]
    assert request["method"] == "GET"
    assert request["url"] == "http://127.0.0.1:{port}/unauthorized".format(
        port=client.port
    )
    assert request["client_ip"] == "127.0.0.1"
    assert response["status"] == 401


async def test_response_trace_header(client, recorder):
    resp = await client.get("/")
    xray_header = resp.headers[http.XRAY_HEADER]
    segment = recorder.emitter.pop()

    expected = "Root=%s" % segment.trace_id
    assert expected in xray_header


async def test_concurrent(client, event_loop, recorder):
    """
    Test multiple concurrent requests
    """
    recorder.emitter = CustomStubbedEmitter()

    async def get_delay():
        resp = await client.get("/delay")
        assert resp.status == 200

    await asyncio.wait(
        [
            get_delay(),
            get_delay(),
            get_delay(),
            get_delay(),
            get_delay(),
            get_delay(),
            get_delay(),
            get_delay(),
            get_delay(),
        ],
        loop=event_loop,
    )

    # Ensure all ID's are different
    ids = [item.id for item in recorder.emitter.local]
    assert len(ids) == len(set(ids))


async def test_disabled_sdk(aiohttp_client, event_loop, recorder):
    """
    Test a normal response when the SDK is disabled.
    """
    global_sdk_config.set_sdk_enabled(False)
    client = await aiohttp_client(ServerTest.app(loop=event_loop))

    resp = await client.get("/")
    assert resp.status == 200

    segment = recorder.emitter.pop()
    assert not segment
