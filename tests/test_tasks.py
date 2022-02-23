"""Test the background task helpers."""

from asyncio import gather
from typing import Optional
from urllib.parse import urlparse

import pytest
from aws_xray_sdk.core import AsyncAWSXRayRecorder
from aws_xray_sdk.core.models.segment import Segment

from xraysink.context import AsyncContext
from xraysink.tasks import xray_task_async

pytestmark = pytest.mark.asyncio


class BaseXrayTaskTests:
    """Core functionality for testing the xray_task_async() decorator."""

    async def _verify_core_segment(
        self, segment: Segment, iserror: bool = False, isfault: bool = False
    ):
        """Verify the core fields of an X-Ray segment."""
        assert not segment.in_progress
        assert getattr(segment, "error", False) == iserror
        assert getattr(segment, "fault", False) == isfault

    async def _verify_http_segment(
        self, segment: Segment, expected_path: Optional[str] = None
    ):
        """Verify the "http" component of an X-Ray segment."""
        request_data = segment.http["request"]

        assert (
            request_data["client_ip"] == "127.0.0.1"
        ), "Should use localhost as client IP for synthetic HTTP request."

        assert request_data["user_agent"].startswith("BackgroundTask")
        assert "xraysink" in request_data["user_agent"]

        url = urlparse(request_data["url"])
        assert url.scheme == "task", "Should use synthetic URL scheme"
        assert (
            url.netloc == "localhost"
        ), "Should use localhost for hostname in synthetic URL"
        if expected_path is not None:
            assert url.path == expected_path, "URL should use synthetic path"

        assert (
            "method" not in request_data
        ), "Should not use HTTP method in synthetic request - that's *too* confusing."
        assert (
            "x_forwarded_for" not in request_data
        ), "Should not provide any indication about HTTP headers in synthetic request."

        assert (
            "response" not in segment.http
        ), "Should not provide any HTTP response data for synthetic request."


class TestXrayTaskAsync(BaseXrayTaskTests):
    """Test the xray_task_async() decorator."""

    async def test_should_create_segment_with_synthetic_http_request(self, recorder):
        # Setup SUT function
        @xray_task_async()
        async def do_something(a, b):
            return a + b

        # Exercise
        func_result = await do_something(1, 2)

        # Verify
        assert func_result == 3, "Function result should be returned"

        segment = recorder.emitter.pop()

        await self._verify_core_segment(segment)
        await self._verify_http_segment(segment, expected_path="/do_something")

    async def test_should_decorate_method(self, recorder):
        # Setup SUT function
        class BoringClass:
            @xray_task_async()
            async def do_something(self, a, b):
                return a + b

        # Exercise
        func_result = await BoringClass().do_something(1, 2)

        # Verify
        assert func_result == 3, "Function result should be returned"

        segment = recorder.emitter.pop()

        await self._verify_core_segment(segment)
        await self._verify_http_segment(
            segment, expected_path="/BoringClass/do_something"
        )

    async def test_should_decorate_classmethod(self, recorder):
        # Setup SUT function
        class BoringClass:
            @xray_task_async()
            @classmethod
            async def do_something(cls, a, b):
                return a + b

        # Exercise
        func_result = await BoringClass.do_something(1, 2)

        # Verify
        assert func_result == 3, "Function result should be returned"

        segment = recorder.emitter.pop()

        await self._verify_core_segment(segment)
        await self._verify_http_segment(
            segment, expected_path="/BoringClass/do_something"
        )

    async def test_should_remove_leading_underscores_for_url_path(self, recorder):
        # Setup SUT function
        @xray_task_async()
        async def _private_function():
            pass

        # Exercise
        await _private_function()

        # Verify
        segment = recorder.emitter.pop()
        await self._verify_http_segment(segment, expected_path="/private_function")

    async def test_should_use_custom_url_path(self, recorder):
        # Setup SUT function
        @xray_task_async(_url_path="something_else")
        async def do_something():
            pass

        # Exercise
        await do_something()

        # Verify
        segment = recorder.emitter.pop()
        await self._verify_http_segment(segment, expected_path="/something_else")

    async def test_should_capture_exception_in_segment(self, recorder):
        # Setup SUT function
        @xray_task_async()
        async def do_something():
            raise ValueError(42)

        # Exercise
        with pytest.raises(ValueError):  # noqa: PT011
            await do_something()

        # Verify
        segment = recorder.emitter.pop()

        await self._verify_core_segment(segment, isfault=True)
        await self._verify_http_segment(segment, expected_path="/do_something")

        exception = segment.cause["exceptions"][0]
        assert exception.type == "ValueError"


class TestXrayTaskAsyncNested(BaseXrayTaskTests):
    """Test the xray_task_async() decorator when nested inside an existing segment."""

    @pytest.fixture()
    def recorder(self, recorder) -> AsyncAWSXRayRecorder:
        # Nested tasks will only work if we are using a well-behaved context
        recorder.configure(context=AsyncContext())
        return recorder

    async def _verify_nested_segment(self, segments, initial_name: str, task_name):
        """Verify the X-Ray entities created by a nested task."""
        assert len(segments) == 2, "Should create another segment for the task"
        initial_segment = [s for s in segments if s.name == initial_name][0]
        task_segment = [s for s in segments if s is not initial_segment][0]

        # Verify initial segment
        await self._verify_core_segment(initial_segment)
        assert (
            len(initial_segment.subsegments) == 1
        ), "Should create a subsegment for the inner task."

        # Verify local subsegment
        subsegment = initial_segment.subsegments[0]
        assert "Create Task" in subsegment.name
        assert task_name in subsegment.name

        request_data = subsegment.http["request"]
        url = urlparse(request_data["url"])
        assert url.scheme == "task", "Should use synthetic URL scheme"
        assert (
            url.netloc == "localhost"
        ), "Should use localhost for hostname in synthetic URL"
        assert task_name in url.path, "URL should use task name in synthetic path"

        # Verify task segment
        await self._verify_core_segment(task_segment)
        await self._verify_http_segment(task_segment, expected_path="/do_something")
        assert task_segment.trace_id == initial_segment.trace_id
        assert task_segment.parent_id == subsegment.id

    async def test_should_set_parent_in_blocking_coroutine(self, recorder):
        # Setup SUT function
        @xray_task_async()
        async def do_something(a, b):
            return a + b

        # Exercise
        async with recorder.in_segment_async("initial_segment"):
            func_result = await do_something(1, 2)

        # Verify
        assert func_result == 3, "Function result should be returned"

        await self._verify_nested_segment(
            recorder.emitter.segments,
            initial_name="initial_segment",
            task_name="do_something",
        )

    async def test_should_set_parent_in_asyncio_task(self, recorder):
        # Setup SUT function
        @xray_task_async()
        async def do_something(a, b):
            return a + b

        # Exercise
        async with recorder.in_segment_async("initial_segment"):
            coro = do_something(1, 2)

        (func_result,) = await gather(coro, return_exceptions=True)

        # Verify
        assert func_result == 3, "Function result should be returned"

        await self._verify_nested_segment(
            recorder.emitter.segments,
            initial_name="initial_segment",
            task_name="do_something",
        )
