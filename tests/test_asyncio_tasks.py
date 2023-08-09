from asyncio import ensure_future
from asyncio import gather
from asyncio import sleep

import pytest
from aws_xray_sdk.core.async_context import AsyncContext as CoreAsyncContext
from aws_xray_sdk.version import VERSION as AWS_XRAY_SDK_VERSION_STRING

from xraysink.context import AsyncContext

pytestmark = pytest.mark.asyncio

AWS_XRAY_SDK_VERSION = list(map(int, AWS_XRAY_SDK_VERSION_STRING.split(".")))

BROKEN_SDK_VERSION = pytest.mark.xfail(
    AWS_XRAY_SDK_VERSION[0] == 2 and AWS_XRAY_SDK_VERSION[1] < 10,
    reason="aws_xray_sdk async context propagation prior to v2.10.0 was broken",
)


@pytest.mark.parametrize(
    "context_class",
    [
        pytest.param(AsyncContext, id="xraysink"),
        pytest.param(CoreAsyncContext, marks=[BROKEN_SDK_VERSION], id="aws_xray_sdk"),
    ],
)
async def test_asyncio_task_subsegments_should_use_parent_task_segment_as_parent(
    recorder, context_class
):
    # Setup
    recorder.configure(context=context_class(use_task_factory=True))

    async def do_task(name: str, sleep_time: float):
        # Emulate a remote call by starting a subsegment and blocking
        async with recorder.in_subsegment_async(name=name):
            await sleep(sleep_time)

    async def broken_task(name: str):
        # Emulate a failure in a remote call by starting a subsegment and raising an exception
        async with recorder.in_subsegment_async(name=name):
            raise Exception(name)

    async def nested_tasks(name: str):
        # Emulate a locally-defined subsegment with remote calls by starting nested subsegments
        async with recorder.in_subsegment_async(name=name):
            _ = await gather(do_task("short-task", 0.05), do_task("long-task", 1.0))

    # Exercise
    async with recorder.in_segment_async(name="top-segment"):
        _ = await gather(
            do_task("short-task", 0.01),
            do_task("long-task", 2.0),
            broken_task("errored-task"),
            do_task("medium-task", 0.5),
            nested_tasks("nested-task"),
            return_exceptions=True,
        )

    # Verify
    segment = recorder.emitter.pop()
    subsegments = {elem.name: elem for elem in segment.subsegments}

    assert (
        len(subsegments) == 5
    ), "Each asyncio task should create a subsegment from the main segment"

    assert (
        subsegments["short-task"].end_time - subsegments["long-task"].start_time
    ) == pytest.approx(0.01, abs=0.2)
    assert not getattr(subsegments["short-task"], "error", False)
    assert not getattr(subsegments["short-task"], "fault", False)

    assert (
        subsegments["medium-task"].end_time - subsegments["long-task"].start_time
    ) == pytest.approx(0.5, abs=0.2)
    assert not getattr(subsegments["medium-task"], "error", False)
    assert not getattr(subsegments["medium-task"], "fault", False)

    assert (
        subsegments["long-task"].end_time - subsegments["long-task"].start_time
    ) == pytest.approx(2.0, abs=0.2)
    assert not getattr(subsegments["long-task"], "error", False)
    assert not getattr(subsegments["long-task"], "fault", False)

    assert not getattr(subsegments["errored-task"], "error", False)
    assert getattr(subsegments["errored-task"], "fault", False)

    nested_task_subsegment = subsegments["nested-task"]
    assert (
        nested_task_subsegment.end_time - nested_task_subsegment.start_time
    ) == pytest.approx(1.0 + 0.05, abs=0.2)
    assert not getattr(nested_task_subsegment, "error", False)
    assert not getattr(nested_task_subsegment, "fault", False)

    nested_subsegments = {
        elem.name: elem for elem in nested_task_subsegment.subsegments
    }
    assert len(nested_subsegments) == 2, "Each nested task should create a subsegment"

    assert (
        nested_subsegments["short-task"].end_time - subsegments["long-task"].start_time
    ) == pytest.approx(0.05, abs=0.2)
    assert not getattr(nested_subsegments["short-task"], "error", False)
    assert not getattr(nested_subsegments["short-task"], "fault", False)

    assert (
        nested_subsegments["long-task"].end_time - subsegments["long-task"].start_time
    ) == pytest.approx(1.0, abs=0.2)
    assert not getattr(nested_subsegments["long-task"], "error", False)
    assert not getattr(nested_subsegments["long-task"], "fault", False)


@pytest.mark.parametrize(
    "context_class",
    [
        pytest.param(AsyncContext, id="xraysink"),
        pytest.param(CoreAsyncContext, marks=[BROKEN_SDK_VERSION], id="aws_xray_sdk"),
    ],
)
async def test_asyncio_task_should_start_segment_when_none_present(
    recorder, context_class
):
    # Setup
    recorder.configure(context=context_class(use_task_factory=True))

    async def do_task(a, b):
        async with recorder.in_segment_async():
            return a + b

    # Exercise
    task = ensure_future(do_task(1, 2))
    result = await task

    # Verify
    assert result == 3

    segment = recorder.emitter.pop()
    assert not segment.in_progress
    assert getattr(segment, "error", False) is False
    assert getattr(segment, "fault", False) is False


@pytest.mark.parametrize(
    "context_class",
    [
        pytest.param(AsyncContext, id="xraysink"),
        pytest.param(CoreAsyncContext, marks=[BROKEN_SDK_VERSION], id="aws_xray_sdk"),
    ],
)
async def test_asyncio_task_should_start_segment_when_previous_segment_closed(
    recorder, context_class
):
    # Setup
    recorder.configure(context=context_class(use_task_factory=True))

    async def do_task(a, b):
        async with recorder.in_segment_async():
            return a + b

    # Setup a completed segment
    async with recorder.in_segment_async():
        pass

    # Exercise
    task = ensure_future(do_task(1, 2))
    result = await task

    # Verify
    assert result == 3

    segment = recorder.emitter.pop()
    assert not segment.in_progress
    assert getattr(segment, "error", False) is False
    assert getattr(segment, "fault", False) is False
