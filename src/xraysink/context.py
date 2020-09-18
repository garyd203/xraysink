"""Recorder context that works well with asyncio."""

import asyncio
import sys

from aws_xray_sdk.core.async_context import AsyncContext as _CoreAsyncContext

_GTE_PY37 = sys.version_info.major == 3 and sys.version_info.minor >= 7


def _context_aware_task_factory(loop, coro):
    """
    Custom task factory function.
    """
    task = asyncio.Task(coro, loop=loop)
    if task._source_traceback:
        del task._source_traceback[-1]

    # Propagate only the X-Ray context to the new task, if present
    if _GTE_PY37:
        current_task = asyncio.current_task(loop=loop)
    else:
        current_task = asyncio.Task.current_task(loop=loop)

    if current_task is not None and hasattr(current_task, "context"):
        new_context = {"entities": list(current_task.context["entities"])}
        setattr(task, "context", new_context)

    return task


class AsyncContext(_CoreAsyncContext):
    """
    Async Context for storing segments.

    Fixes bugs in the parent class when using asyncio tasks.
    """

    def __init__(self, *args, use_task_factory=True, **kwargs):
        super().__init__(self, *args, use_task_factory=use_task_factory, **kwargs)

        if use_task_factory:
            self._loop.set_task_factory(_context_aware_task_factory)
