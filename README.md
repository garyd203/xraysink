# xraysink (aka xray-asyncio)
Extra AWS X-Ray instrumentation for asyncio Python libraries that are not
(yet) supported by the official
[aws_xray_sdk](https://github.com/aws/aws-xray-sdk-python) library.


## Integrations Supported
* Generic ASGI-compatible tracing middleware for *any* ASGI-compliant web
  framework. This has been tested with:
  - [aiohttp server](https://docs.aiohttp.org/en/stable/)
  - [FastAPI](https://fastapi.tiangolo.com/)


## Installation
xraysink is distributed as a standard python package through
[pypi](https://pypi.org/), so you can install it with your favourite Python
package manager. For example:

    pip install xraysink 


## How to use

### FastAPI
Instrument incoming requests in your FastAPI web server by adding the `xray_middleware`. For example:

    # Basic asyncio X-Ray configuration
    xray_recorder.configure(context=AsyncContext(), service="my-cute-little-service")
    
    # Create a FastAPI app with various middleware
    app = FastAPI()
    app.add_middleware(MyTracingDependentMiddleware)  # Any middleware that is added earlier will have the X-Ray tracing context available to it
    app.add_middleware(BaseHTTPMiddleware, dispatch=xray_middleware)


### Background Tasks
If your process starts background tasks that make network calls (eg. to the
database or an API in another service), then each execution of one of those
tasks should be treated as a new X-Ray trace. Indeed, if you don't do so then
you will likely get context_missing errors.

An async function that implements a background task can be easily instrumented
using the `@xray_task_async()` decorator, like so:

    # Basic asyncio X-Ray configuration
    xray_recorder.configure(context=AsyncContext(), service="my-cute-little-service")
    
    # Any call to this function will start a new X-Ray trace
    @xray_task_async()
    async def cleanup_stale_tokens():
        await database.get_table("tokens").delete(age__gt=1)
    
    schedule_recurring_task(cleanup_stale_tokens)


## Licence
This project uses the Apache 2.0 licence, to make it compatible with
[aws_xray_sdk](https://github.com/aws/aws-xray-sdk-python), the
primary library for integrating with AWS X-Ray.
