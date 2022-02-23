"""Test the ASGI middleware with all asyncio server's."""

import asyncio
from datetime import datetime
from typing import Union
from urllib.parse import urlparse

import aiohttp.web_app
import pytest
import requests
from aiohttp.pytest_plugin import aiohttp_client  # noqa: F401
from async_asgi_testclient import TestClient
from aws_xray_sdk import global_sdk_config
from aws_xray_sdk.core.models import http
from aws_xray_sdk.core.models.segment import Segment
from starlette.status import HTTP_200_OK
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from ._aiohttp import AioHttpServerFactory
from ._fastapi import fastapi_native_middleware_factory


pytestmark = pytest.mark.asyncio


# aiohttp Testing
# ---------------
#
# We import just the client helper fixture from aiohttp, without polluting our
# fixture namespace with all the cray-cray in the `pytest-aiohttp` pytest
# plugin (like yet another `loop`).
#
# We also have to inject a `loop` fixture based on the normal `event_loop` fixture,
# since aiohttp_client has this as a fixture dependency
@pytest.fixture()
async def loop(event_loop):
    return event_loop


@pytest.fixture(
    params=[
        pytest.param(AioHttpServerFactory.app, id="aiohttp"),
        pytest.param(fastapi_native_middleware_factory, id="fastapi"),
    ]
)
async def client(request, aiohttp_client):  # noqa: F811
    """Get a client for each of the server frameworks under test."""
    appfactory = request.param
    app = appfactory()

    if isinstance(app, aiohttp.web_app.Application):
        # Note that aiohttp is not actually ASGI-compliant, so we need to use
        # a custom client (not the usual `async_asgi_testclient.AsyncTestClient`)
        client = await aiohttp_client(AioHttpServerFactory.app())
        yield client
    else:
        # A normal ASGI-compliant app
        async with TestClient(app) as client:
            # Set the default request host to be the same as that for
            # `aiohttp_client` (rather than the usual "localhost"), since it's
            # difficult to modify the `aiohttp_client` one.
            client.headers["host"] = "127.0.0.1"

            yield client


class TestRequestHandler:
    """Verify that an instrumented web server handles requests correctly."""

    async def _verify_http_status(
        self, response: Union[requests.Response, aiohttp.ClientResponse], status: int
    ):
        """Verify the status code on a response."""
        if isinstance(response, aiohttp.ClientResponse):
            assert response.status == status, await response.text()
        elif hasattr(response, "status_code"):
            assert response.status_code == status, response.text
        else:
            pytest.fail("Unknown response object type")

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
        await self._verify_http_status(server_response, HTTP_200_OK)

        segment = recorder.emitter.pop()
        assert not segment.in_progress
        assert not getattr(segment, "error", False)
        assert not getattr(segment, "fault", False)

        self._verify_xray_request(segment, "/")
        self._verify_xray_response(segment, HTTP_200_OK)

    async def test_should_use_segmentid_in_http_header(self, client, recorder):
        # Exercise
        server_response = await client.get("/")

        # Verify
        segment = recorder.emitter.pop()
        expected_root = f"Root={segment.trace_id}"

        xray_header = server_response.headers[http.XRAY_HEADER]
        assert expected_root in xray_header

    async def test_should_record_client_ip_from_x_forwarded_for_header(
        self, client, recorder
    ):
        fake_ip = "10.1.2.3"

        # Exercise
        server_response = await client.get("/", headers={"X-Forwarded-For": fake_ip})

        # Verify
        await self._verify_http_status(server_response, HTTP_200_OK)

        segment = recorder.emitter.pop()
        self._verify_xray_request(segment, "/", client_ip=fake_ip, x_forwarded_for=True)
        self._verify_xray_response(segment, HTTP_200_OK)

    async def test_should_record_response_content_length(self, client, recorder):
        # Exercise
        server_response = await client.get("/?content_length=100")

        # Verify
        await self._verify_http_status(server_response, HTTP_200_OK)

        segment = recorder.emitter.pop()
        self._verify_xray_request(segment, "/")
        self._verify_xray_response(segment, HTTP_200_OK, content_length=100)

    @pytest.mark.parametrize(
        "path",
        [
            "/client_error_as_response",
            "/client_error_as_http_exception",
            "/client_error_from_handled_exception",
        ],
    )
    async def test_should_record_4xx_client_error(self, client, recorder, path):
        if (
            "aiohttp" in type(client).__module__
            and path == "/client_error_from_handled_exception"
        ):
            pytest.skip(
                "aiohttp doesn't have custom application exception handler within the framework"
            )

        # Exercise
        server_response = await client.get(path)

        # Verify
        await self._verify_http_status(server_response, HTTP_422_UNPROCESSABLE_ENTITY)

        segment = recorder.emitter.pop()
        assert not segment.in_progress
        assert segment.error
        assert not getattr(
            segment, "fault", False
        ), "A client error is not a server fault"

        self._verify_xray_request(segment, path)
        self._verify_xray_response(segment, HTTP_422_UNPROCESSABLE_ENTITY)

    async def test_should_record_unauthorized_error(self, client, recorder):
        # Exercise
        server_response = await client.get("/unauthorized")

        # Verify
        await self._verify_http_status(server_response, HTTP_401_UNAUTHORIZED)

        segment = recorder.emitter.pop()
        assert not segment.in_progress
        assert segment.error
        assert not getattr(
            segment, "fault", False
        ), "A client error is not a server fault"

        self._verify_xray_request(segment, "/unauthorized")
        self._verify_xray_response(segment, HTTP_401_UNAUTHORIZED)

    async def test_should_record_unhandled_server_exception(self, client, recorder):
        # Exercise
        #
        # Note that some test clients (eg. async_asgi_testclient) will
        # deliberately unpack the original exception in an ASGI "err" response
        # and re-raise it for us. So we need to handle both types of response.
        if isinstance(client, TestClient):
            with pytest.raises(KeyError):
                _ = await client.get("/exception")
        else:
            server_response = await client.get("/exception")
            await self._verify_http_status(
                server_response, HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Verify
        segment = recorder.emitter.pop()
        assert not segment.in_progress

        assert not getattr(
            segment, "error", False
        ), "A server fault is not a client error"
        assert segment.fault
        exception = segment.cause["exceptions"][0]
        assert exception.type == "KeyError"

        self._verify_xray_request(segment, "/exception")
        self._verify_xray_response(segment, HTTP_500_INTERNAL_SERVER_ERROR)

    async def test_should_record_different_segment_for_each_concurrent_request(
        self, client, recorder
    ):
        # Setup
        async def get_response_with_delay():
            test_start = datetime.utcnow()
            server_response = await client.get("/delay")
            assert (datetime.utcnow() - test_start).total_seconds() > 0.3
            await self._verify_http_status(server_response, HTTP_200_OK)

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
        ids = [item.id for item in recorder.emitter.segments]
        assert len(ids) == len(set(ids)), "All ID's should be different"

    async def test_should_not_record_when_sdk_is_disabled(self, client, recorder):
        # Setup
        global_sdk_config.set_sdk_enabled(False)

        # Exercise
        server_response = await client.get("/")

        # Verify
        await self._verify_http_status(server_response, HTTP_200_OK)

        segment = recorder.emitter.pop()
        assert not segment
