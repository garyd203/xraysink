"""Tools for tracing background tasks."""

import inspect
from typing import Optional

import wrapt
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core.models import http

from . import __version__ as xraysink_version


def xray_task_async():
    """Decorator for a coroutine that starts a new traced background task.

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
        annotations: Annotations to attach ot the created segment.
        metadata: Dictionary of metadata to attach to the created segment.
        name: Override the name used for the segment (not recommended). By
            default the X-Ray SDK will use the service name that has been
            configured for this process.
    """
    task_path: Optional[str] = None

    @wrapt.decorator
    async def wrapper(wrapped, instance, args, kwargs):
        # Determine task path just once
        nonlocal task_path
        if task_path is None:
            if instance is None:
                task_path = wrapped.__name__
            else:
                if inspect.isclass(instance):
                    task_path = "/".join([instance.__name__, wrapped.__name__])
                else:
                    task_path = "/".join(
                        [instance.__class__.__name__, wrapped.__name__]
                    )

        # Start a segment from scratch (ie. start a new trace)
        async with xray_recorder.in_segment_async() as segment:
            # Add background task info to segment as a synthetic HTTP request
            segment.put_http_meta(http.URL, "task://localhost/" + task_path)
            segment.put_http_meta(http.CLIENT_IP, "127.0.0.1")
            segment.put_http_meta(
                http.USER_AGENT, f"BackgroundTask xraysink/{xraysink_version}"
            )

            return await wrapped(*args, **kwargs)

    return wrapper
