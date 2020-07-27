"""Various X-Ray middleware's for different ASGI-like server frameworks."""

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core.models import http
from aws_xray_sdk.core.models.segment import Segment
from aws_xray_sdk.core.models.trace_header import TraceHeader
from aws_xray_sdk.core.utils import stacktrace
from aws_xray_sdk.ext.util import calculate_sampling_decision
from aws_xray_sdk.ext.util import calculate_segment_name
from aws_xray_sdk.ext.util import construct_xray_header
from aws_xray_sdk.ext.util import prepare_response_header

# See if app-framework-specific exceptions are present, and substitute with a
# dummy implementation. These are only used for `isinstance` checking within
# this module, so this is safe.
try:
    from aiohttp.web_exceptions import HTTPException as AioHttpWebException
except ImportError:

    class AioHttpWebException(Exception):
        def __init__(self, *args, **kwargs):
            raise TypeError("Fake exception should not be instantiated")


# Middleware functions for aiohttp must be decorated with a aiohttp-specific
# decorator. The decorator itself is fairly innocuous, but we need to work
# around it for situations where aiohttp is not present.
try:
    from aiohttp.web import middleware as aiohttp_middleware
except ImportError:

    def aiohttp_middleware(func):
        return func


@aiohttp_middleware
async def xray_middleware(request, handler):
    """
    Main middleware function, deals with all the X-Ray segment logic
    """
    # Create X-Ray headers
    xray_header = construct_xray_header(request.headers)

    # Get name of service or generate a dynamic one from host
    name = calculate_segment_name(
        request.headers["host"].split(":", 1)[0], xray_recorder
    )

    sampling_req = {
        "host": request.headers["host"],
        "method": request.method,
        "path": _get_request_path(request),
        "service": name,
    }

    sampling_decision = calculate_sampling_decision(
        trace_header=xray_header, recorder=xray_recorder, sampling_req=sampling_req
    )

    # Start a segment
    segment = xray_recorder.begin_segment(
        name=name,
        traceid=xray_header.root,
        parent_id=xray_header.parent,
        sampling=sampling_decision,
    )
    try:
        segment.save_origin_trace_header(xray_header)

        # Store request metadata in the current segment
        segment.put_http_meta(http.URL, str(request.url))
        segment.put_http_meta(http.METHOD, request.method)

        if "User-Agent" in request.headers:
            segment.put_http_meta(http.USER_AGENT, request.headers["User-Agent"])

        if "X-Forwarded-For" in request.headers:
            segment.put_http_meta(http.CLIENT_IP, request.headers["X-Forwarded-For"])
            segment.put_http_meta(http.X_FORWARDED_FOR, True)
        elif "remote_addr" in request.headers:
            segment.put_http_meta(http.CLIENT_IP, request.headers["remote_addr"])
        elif "remote-addr" in request.headers:
            # NB: hyphenated variation of remote_addr.
            # Don't mistakenly think they are the same :)
            segment.put_http_meta(http.CLIENT_IP, request.headers["remote-addr"])
        elif hasattr(request, "remote"):
            segment.put_http_meta(http.CLIENT_IP, request.remote)
        elif hasattr(request, "client") and request.client.host is not None:
            segment.put_http_meta(http.CLIENT_IP, request.client.host)

        # Call next middleware or request handler
        try:
            response = await handler(request)
            _record_response(segment, xray_header, response)
        except Exception as ex:
            _record_exception(segment, xray_header, ex)
            raise
    finally:
        xray_recorder.end_segment()

    return response


def _get_request_path(request) -> str:
    """Get the path from from any type of request object."""
    if hasattr(request, "path"):
        # aiohttp-style
        return request.path
    elif hasattr(request, "url"):
        # starlette-style
        return request.url.path
    raise TypeError(f"Don't know how to find the path for {type(request)}")


def _get_response_status(response) -> int:
    """Get the HTTP status code from any type of response object."""
    if hasattr(response, "status"):
        # aiohttp-style
        return response.status
    elif hasattr(response, "status_code"):
        # starlette-style
        return response.status_code
    raise TypeError(f"Don't know how to find the path for {type(response)}")


def _record_exception(segment: Segment, xray_header: TraceHeader, ex: Exception):
    """Record an exception from the web app.

    Note that different web frameworks take different approaches to how
    exceptions are passed back to a user middleware like ours. For example:
    * aiohttp can use exceptions to signal non-success HTTP responses, which
      will be visible to middleware.
    * fastapi explicitly puts it's well-known exception handling (including
      HTTPException conversion) in front of any middleware, so any exceptions
      at this point are genuine server failures.
    """
    # The aiohttp server framework will use exceptions that act as a response.
    #
    # Note that the aiohttp client uses a different exception hierarchy, so
    # these errors will only occur when we are instrumenting an aiohttp
    # application, regardless of how the application code makes downstream
    # HTTP requests.
    if isinstance(ex, AioHttpWebException):
        _record_response(segment, xray_header, ex)
        return

    # Default behaviour - assume this is a server error
    segment.put_http_meta(http.STATUS, 500)
    stack = stacktrace.get_stacktrace(limit=xray_recorder.max_trace_back)
    segment.add_exception(ex, stack)


def _record_response(segment: Segment, xray_header: TraceHeader, response):
    """Record a HTTP response from the web app."""
    segment.put_http_meta(http.STATUS, _get_response_status(response))
    if "Content-Length" in response.headers:
        length = int(response.headers["Content-Length"])
        segment.put_http_meta(http.CONTENT_LENGTH, length)

    header_str = prepare_response_header(xray_header, segment)
    response.headers[http.XRAY_HEADER] = header_str
