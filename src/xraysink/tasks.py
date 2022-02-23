"""Tools for tracing background tasks."""

import inspect
import re
from asyncio import ensure_future
from typing import Optional

import wrapt
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core.models import http
from aws_xray_sdk.core.models.subsegment import Subsegment

from . import __version__ as xraysink_version
from .util import has_current_trace

#: URL scheme for the synthetic URL's used by background tasks.
TASK_SCHEME: str = "task"

#: Format string for the synthetic URL's used by background tasks.
TASK_URL_FORMAT: str = TASK_SCHEME + "://localhost/{task_path}"  # noqa: FS003


def xray_task_async(*, _url_path: Optional[str] = None):
    """Decorator for a coroutine that executes an independent traced task.

    If there is an existing trace segment, we create a new segment using that
    segment as the parent (note that we are unable to create a subsegment,
    because we can't ensure that the subsegment would finish whilst the parent
    segment is still active; additionally, the purpose of this decorator is
    to manage *independent* segments), and additionally execute the decorated
    coroutine in a task. Otherwise, we originate a new trace.

    Notes:
        The X-Ray data model doesn't really allow for an internally originated
        trace - it is assumed that everything is a HTTP request.

        The nearest analogue in existing usage is a Lambda invoke by a
        CloudWatch event source, like a scheduled event. In that case, the
        initial segment is shown as an incoming HTTP request (with very
        limited HTTP data) to the Lambda service (aside: it is plausible that
        is what actually happens), and the Lambda invoke is shown as a
        subsequent segment with no HTTP data or other special fields.

        However, the X-Ray console Overview and List screens provide a very
        poor experience for traces that don't have sufficient HTTP data in
        their initial segment. So to workaround this, we represent each
        background task as the handler for a synthetic HTTP request in a
        made-up URL scheme.

    Params:
        _url_path: String to use as the path of the synthetic URL. The default
            value is determined from the name of the decorated function.
    """
    # Cached task_name to use for every execution of this decorated function
    task_path: Optional[str] = _url_path
    if task_path is not None:
        task_path = task_path.lstrip("/")

    @wrapt.decorator
    def wrapper(wrapped, instance, args, kwargs):
        # The wrapper function returned from this decorator is intentionally
        # non-async. This is because it needs to access the trace context at
        # the time the function is called, not when the target coroutine is
        # actually executed.

        # Determine task path just once
        nonlocal task_path
        if task_path is None:
            task_path = _get_task_path(wrapped, instance)

        # Execute the target wrapped function
        if has_current_trace():
            # Create a minimal subsegment as a parent for executing the task
            with xray_recorder.in_subsegment(
                name=f"Create Task: {task_path}", namespace="local"
            ) as subsegment:
                subsegment.put_http_meta(
                    http.URL, TASK_URL_FORMAT.format(task_path=task_path)
                )

                coro = _execute_task_in_segment(
                    wrapped, args, kwargs, task_path, parent=subsegment
                )

                # We always execute the wrapped function in an asyncio task,
                # because it needs to be in it's own segment and the X-Ray
                # context is intended to handle only 1 segment at a time.
                return ensure_future(coro)
        else:
            # Start a segment from scratch (ie. start a new trace)
            return _execute_task_in_segment(wrapped, args, kwargs, task_path)

    return wrapper


async def _execute_task_in_segment(
    wrapped, args, kwargs, task_path, parent: Subsegment = None
):
    """Execute a wrapped function inside a new X-Ray segment"""
    # Setup trace context from parent, if necessary
    segment_params = {}
    if parent is not None:
        xray_recorder.clear_trace_entities()
        segment_params.update(
            traceid=parent.trace_id, parent_id=parent.id, sampling=parent.sampled
        )

    # Create a new segment for the task
    async with xray_recorder.in_segment_async(**segment_params) as segment:
        # Add background task info to segment as a synthetic HTTP request
        segment.put_http_meta(http.URL, TASK_URL_FORMAT.format(task_path=task_path))
        segment.put_http_meta(http.CLIENT_IP, "127.0.0.1")
        segment.put_http_meta(
            http.USER_AGENT, f"BackgroundTask xraysink/{xraysink_version}"
        )

        return await wrapped(*args, **kwargs)


def _get_task_path(wrapped, instance) -> str:
    """Get the synthetic URL path for a task, based on the `wrapt` parameters."""
    funcname = wrapped.__name__
    if funcname.startswith("_") and not funcname.endswith("_"):
        funcname = re.sub(r"^_+", repl="", string=funcname, count=1)

    if instance is None:
        return funcname
    else:
        if inspect.isclass(instance):
            return "/".join([instance.__name__, funcname])
        else:
            return "/".join([instance.__class__.__name__, funcname])
