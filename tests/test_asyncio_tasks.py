from asyncio import ensure_future
from asyncio import gather
from asyncio import sleep

import pytest
from pytest import approx

from xraysink.context import AsyncContext

pytestmark = pytest.mark.asyncio


async def test_asyncio_task_subsegments_should_use_parent_task_segment_as_parent(
    recorder,
):
    # Setup
    recorder.configure(context=AsyncContext(use_task_factory=True))

    async def do_task(name: str, sleep_time: float):
        # Emulate a remote call by starting a subsegment and blocking
        async with recorder.in_subsegment_async(name=name):
            await sleep(sleep_time)

    async def broken_task(name: str):
        # Emulate a remote call by starting a subsegment and blocking
        async with recorder.in_subsegment_async(name=name):
            raise Exception(name)

    # Exercise
    async with recorder.in_segment_async(name="top-segment"):
        _ = await gather(
            do_task("short-task", 0.01),
            do_task("long-task", 2.0),
            broken_task("errored-task"),
            do_task("medium-task", 0.5),
            return_exceptions=True,
        )

    # Verify
    segment = recorder.emitter.pop()
    subsegments = {elem.name: elem for elem in segment.subsegments}

    assert (
        len(subsegments) == 4
    ), "Each asyncio task should create a subsegment from the main segment "

    assert (
        subsegments["short-task"].end_time - subsegments["long-task"].start_time
    ) == approx(0.01, abs=0.1)
    assert not getattr(subsegments["short-task"], "error", False)
    assert not getattr(subsegments["short-task"], "fault", False)

    assert (
        subsegments["medium-task"].end_time - subsegments["long-task"].start_time
    ) == approx(0.5, abs=0.1)
    assert not getattr(subsegments["medium-task"], "error", False)
    assert not getattr(subsegments["medium-task"], "fault", False)

    assert (
        subsegments["long-task"].end_time - subsegments["long-task"].start_time
    ) == approx(2.0, abs=0.1)
    assert not getattr(subsegments["long-task"], "error", False)
    assert not getattr(subsegments["long-task"], "fault", False)

    assert not getattr(subsegments["errored-task"], "error", False)
    assert getattr(subsegments["errored-task"], "fault", False)


async def test_asyncio_task_should_start_segment_when_none_present(recorder):
    # Setup
    recorder.configure(context=AsyncContext(use_task_factory=True))

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


async def test_asyncio_task_should_start_segment_when_previous_segment_closed(recorder):
    # Setup
    recorder.configure(context=AsyncContext(use_task_factory=True))

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
