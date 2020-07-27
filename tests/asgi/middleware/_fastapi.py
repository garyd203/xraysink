import asyncio
from typing import Optional

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from xraysink.asgi.middleware import xray_middleware

__all__ = ["fastapi_native_middleware_factory"]


async def handle_request(content_length: Optional[int] = None) -> str:
    if content_length is not None:
        return "A" * (content_length - 2)

    return "ok"


async def handle_with_keyerror() -> str:
    return {}["key"]


async def handle_with_delay() -> str:
    await asyncio.sleep(0.3)
    return "ok"


async def generic_exception_handler(request, ex):
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR, content={"message": str(ex)}
    )


def fastapi_native_middleware_factory():
    """Create a FastAPI app that uses native-style middleware."""
    app = FastAPI()

    # Add an explicit handler for our KeyError, as otherwise the generic
    # error handler will send an "err" response that the test client
    # converts back into an exception, thus breaking the test case.
    app.add_exception_handler(KeyError, generic_exception_handler)

    app.add_middleware(BaseHTTPMiddleware, dispatch=xray_middleware)

    app.add_api_route("/", handle_request)
    app.add_api_route(
        "/client_error", handle_request, status_code=HTTP_422_UNPROCESSABLE_ENTITY
    )
    app.add_api_route("/delay", handle_with_delay)
    app.add_api_route("/exception", handle_with_keyerror)
    app.add_api_route(
        "/unauthorized", handle_request, status_code=HTTP_401_UNAUTHORIZED
    )

    return app
