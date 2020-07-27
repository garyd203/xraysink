import asyncio
from typing import Optional

from fastapi import FastAPI
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from xraysink.asgi.middleware import xray_middleware


__all__ = ["fastapi_native_middleware_factory"]


async def handle_request(content_length: Optional[int] = None) -> str:
    if content_length is not None:
        return "A" * (content_length - 2)

    return "ok"


async def handle_with_delay() -> str:
    await asyncio.sleep(0.3)
    return "ok"


async def handle_with_keyerror() -> str:
    return {}["key"]


async def handle_with_http_exception() -> str:
    raise HTTPException(HTTP_422_UNPROCESSABLE_ENTITY, "Whoopsie")


async def handle_with_indexerror() -> str:
    return [][0]


async def client_induced_exception_handler(request, ex):
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY, content={"message": str(ex)}
    )


def fastapi_native_middleware_factory():
    """Create a FastAPI app that uses native-style middleware."""
    app = FastAPI()

    # Exception handler for `/client_error_from_handled_exception`
    app.add_exception_handler(IndexError, client_induced_exception_handler)

    app.add_middleware(BaseHTTPMiddleware, dispatch=xray_middleware)

    app.add_api_route("/", handle_request)
    app.add_api_route("/client_error_as_http_exception", handle_with_http_exception)
    app.add_api_route(
        "/client_error_as_response",
        handle_request,
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
    )
    app.add_api_route("/client_error_from_handled_exception", handle_with_indexerror)
    app.add_api_route("/delay", handle_with_delay)
    app.add_api_route("/exception", handle_with_keyerror)
    app.add_api_route(
        "/unauthorized", handle_request, status_code=HTTP_401_UNAUTHORIZED
    )

    return app
