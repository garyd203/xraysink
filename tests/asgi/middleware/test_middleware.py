"""Test the ASGI middleware with all asyncio server's."""

import asyncio
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from aws_xray_sdk import global_sdk_config
from aws_xray_sdk.core.async_context import AsyncContext
from aws_xray_sdk.core.emitters.udp_emitter import UDPEmitter
from aws_xray_sdk.core.models import http
from aws_xray_sdk.core.models.segment import Segment
from starlette.status import HTTP_200_OK
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.status import HTTP_404_NOT_FOUND
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from ._aiohttp import AioHttpServerFactory
from ...xray_util import get_new_stubbed_recorder

pytestmark = pytest.mark.asyncio


# Import just the client helper fixture from aiohttp, without polluting our
# fixture namespace with all the cray-cray in the `pytest-aiohttp` pytest
# plugin (like yet another `loop`).
#
# noinspection PyUnresolvedReferences
from aiohttp.pytest_plugin import aiohttp_client


# Inject a `loop` fixture based on the normal `event_loop` fixture,
# since aiohttp_client has this as a fixture dependency
@pytest.fixture
async def loop(event_loop):
    yield event_loop


@pytest.fixture
async def client(aiohttp_client):
    # Note that aiohttp is not actually ASGI-compliant, so we need to use
    # a custom client (not the usual `async_asgi_testclient.AsyncTestClient`)
    client = await aiohttp_client(AioHttpServerFactory.app())
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


class TestRequestHandler:
    """Verify that an instrumented web server handles requests correctly."""

    def _verify_xray_request(
        self,
        segment: Segment,
        path: str,
        method: str = "GET",
        client_ip: str = "127.0.0.1",
        hostname: str = "127.0.0.1",
        **optional_properties,
    ):
        """Verify the request in the X-Ray segment matches the HTTP request details."""
        xray_request = segment.http["request"]

        assert xray_request["client_ip"] == client_ip
        assert xray_request["method"] == method

        url = urlparse(xray_request["url"])
        assert url.scheme == "http", "scheme should be in URL"
        assert url.netloc.startswith(hostname), "URL should contain hostname"
        assert url.path == path, "URL should contain path"

        for name, value in optional_properties.items():
            assert name in xray_request, f"Optional property f{name} should be present"
            assert xray_request[name] == value

    def _verify_xray_response(
        self, segment: Segment, status: int, **optional_properties
    ):
        """Verify the request in the X-Ray segment matches the HTTP request details."""
        xray_response = segment.http["response"]

        assert xray_response["status"] == status

        for name, value in optional_properties.items():
            assert name in xray_response, f"Optional property f{name} should be present"
            assert xray_response[name] == value

    async def test_should_create_segment_for_normal_response(self, client, recorder):
        # Exercise
        server_response = await client.get("/")

        # Verify
        assert server_response.status == HTTP_200_OK

        segment = recorder.emitter.pop()
        assert not segment.in_progress
        self._verify_xray_request(segment, "/")
        self._verify_xray_response(segment, HTTP_200_OK)

    async def test_should_use_segmentid_in_http_header(self, client, recorder):
        # Exercise
        server_response = await client.get("/")

        # Verify
        segment = recorder.emitter.pop()
        expected_root = "Root=%s" % segment.trace_id

        xray_header = server_response.headers[http.XRAY_HEADER]
        assert expected_root in xray_header

    async def test_should_record_client_ip_from_x_forwarded_for_header(
        self, client, recorder
    ):
        fake_ip = "10.1.2.3"

        # Exercise
        server_response = await client.get("/", headers={"X-Forwarded-For": fake_ip})

        # Verify
        assert server_response.status == HTTP_200_OK

        segment = recorder.emitter.pop()
        self._verify_xray_request(segment, "/", client_ip=fake_ip, x_forwarded_for=True)
        self._verify_xray_response(segment, HTTP_200_OK)

    async def test_should_record_response_content_length(self, client, recorder):
        # Exercise
        server_response = await client.get("/?content_length=100")

        # Verify
        assert server_response.status == HTTP_200_OK

        segment = recorder.emitter.pop()
        self._verify_xray_request(segment, "/")
        self._verify_xray_response(segment, HTTP_200_OK, content_length=100)

    async def test_should_record_4xx_client_error(self, client, recorder):
        # Exercise
        server_response = await client.get("/error")

        # Verify
        assert server_response.status == HTTP_404_NOT_FOUND

        segment = recorder.emitter.pop()
        assert not segment.in_progress
        assert segment.error

        self._verify_xray_request(segment, "/error")
        self._verify_xray_response(segment, HTTP_404_NOT_FOUND)

    async def test_should_record_unauthorized_error(self, client, recorder):
        # Exercise
        server_response = await client.get("/unauthorized")

        # Verify
        assert server_response.status == HTTP_401_UNAUTHORIZED

        segment = recorder.emitter.pop()
        assert not segment.in_progress
        assert segment.error

        self._verify_xray_request(segment, "/unauthorized")
        self._verify_xray_response(segment, HTTP_401_UNAUTHORIZED)

    async def test_should_record_server_exception(self, client, recorder):
        # Exercise
        server_response = await client.get("/exception")

        # Verify
        assert server_response.status == HTTP_500_INTERNAL_SERVER_ERROR

        segment = recorder.emitter.pop()
        assert not segment.in_progress

        self._verify_xray_request(segment, "/exception")
        self._verify_xray_response(segment, HTTP_500_INTERNAL_SERVER_ERROR)

        assert segment.fault
        exception = segment.cause["exceptions"][0]
        assert exception.type == "KeyError"

    async def test_should_record_different_segment_for_each_concurrent_request(
        self, client, recorder
    ):
        # Setup
        recorder.emitter = CustomStubbedEmitter()

        async def get_response_with_delay():
            server_response = await client.get("/delay")
            assert server_response.status == HTTP_200_OK

        # Exercise
        await asyncio.wait(
            [
                get_response_with_delay(),
                get_response_with_delay(),
                get_response_with_delay(),
                get_response_with_delay(),
                get_response_with_delay(),
                get_response_with_delay(),
                get_response_with_delay(),
                get_response_with_delay(),
                get_response_with_delay(),
            ]
        )

        # Verify
        ids = [item.id for item in recorder.emitter.local]
        assert len(ids) == len(set(ids)), "All ID's should be different"

    async def test_should_not_record_when_sdk_is_disabled(self, client, recorder):
        # Setup
        global_sdk_config.set_sdk_enabled(False)

        # Exercise
        server_response = await client.get("/")

        # Verify
        assert server_response.status == 200

        segment = recorder.emitter.pop()
        assert not segment
