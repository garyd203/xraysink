"""Various X-Ray middleware's for different ASGI-like server frameworks."""

from aiohttp import web
from aiohttp.web_exceptions import HTTPException
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core.models import http
from aws_xray_sdk.core.utils import stacktrace
from aws_xray_sdk.ext.util import calculate_sampling_decision
from aws_xray_sdk.ext.util import calculate_segment_name
from aws_xray_sdk.ext.util import construct_xray_header
from aws_xray_sdk.ext.util import prepare_response_header


@web.middleware
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
        segment.put_http_meta(http.CLIENT_IP, request.headers["remote-addr"])
    elif hasattr(request, "remote"):
        segment.put_http_meta(http.CLIENT_IP, request.remote)
    elif hasattr(request, "client") and request.client.host is not None:
        segment.put_http_meta(http.CLIENT_IP, request.client.host)

    try:
        # Call next middleware or request handler
        response = await handler(request)
    except HTTPException as exc:
        # Non 2XX responses are raised as HTTPExceptions
        response = exc
        raise
    except Exception as err:
        # Store exception information including the stacktrace to the segment
        response = None
        segment.put_http_meta(http.STATUS, 500)
        stack = stacktrace.get_stacktrace(limit=xray_recorder.max_trace_back)
        segment.add_exception(err, stack)
        raise
    finally:
        if response is not None:
            segment.put_http_meta(http.STATUS, _get_response_status(response))
            if "Content-Length" in response.headers:
                length = int(response.headers["Content-Length"])
                segment.put_http_meta(http.CONTENT_LENGTH, length)

            header_str = prepare_response_header(xray_header, segment)
            response.headers[http.XRAY_HEADER] = header_str

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
