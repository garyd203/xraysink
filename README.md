# xraysink

<p align="center">
    <a href="https://pypi.org/project/xraysink/">
        <img src="https://img.shields.io/pypi/v/xraysink.svg" alt="Package version">
    </a>
    <a href="https://pypi.org/project/xraysink/">
        <img src="https://img.shields.io/pypi/pyversions/xraysink.svg" alt="Python versions">
    </a>
    <a href="https://pypi.org/project/xraysink/">
        <img src="https://img.shields.io/pypi/dm/xraysink.svg" alt="Monthly downloads">
    </a>
</p>

Extra AWS X-Ray instrumentation to use distributed tracing with asyncio Python
libraries that are not (yet) supported by the official
[aws_xray_sdk](https://github.com/aws/aws-xray-sdk-python) library.


## Integrations Supported
* Generic ASGI-compatible tracing middleware for *any* ASGI-compliant web
  framework. This has been tested with:
  - [aiohttp server](https://docs.aiohttp.org/en/stable/)
  - [FastAPI](https://fastapi.tiangolo.com/)
* asyncio [Task's](https://docs.python.org/3/library/asyncio-task.html)
* Background jobs/tasks

## Installation
xraysink is distributed as a standard python package through
[pypi](https://pypi.org/), so you can install it with your favourite Python
package manager. For example:

    pip install xraysink


## How to use
`xraysink` augments the functionality provided by `aws_xray_sdk`. Before
using the tools in `xraysink`, you first need to configure `aws_xray_sdk` -
this will probably involve calling `xray_recorder.configure()` when your
process starts, and optionally `aws_xray_sdk.core.patch()`.

Extra instrumentation provided by `xraysink` is described below.

### FastAPI
Instrument incoming requests in your FastAPI web server by adding the
`xray_middleware` to your app. For example, you could do:

    from starlette.middleware.base import BaseHTTPMiddleware
    from xraysink.asgi.middleware import xray_middleware
    
    # Standard asyncio X-Ray configuration, customise as you choose
    xray_recorder.configure(context=AsyncContext(), service="my-cute-little-service")
    
    # Create a FastAPI app with various middleware
    app = FastAPI()
    app.add_middleware(MyTracingDependentMiddleware)  # Any middleware that is added earlier will have the X-Ray tracing context available to it
    app.add_middleware(BaseHTTPMiddleware, dispatch=xray_middleware)


### Asyncio Tasks
If you start asyncio [Task's](https://docs.python.org/3/library/asyncio-task.html)
from a standard request handler, then the AWS X-Ray SDK will not correctly
instrument any outgoing requests made inside those Tasks.

Use the fixed `AsyncContext` from `xraysink` as a drop-in replacement, like so:

    from aws_xray_sdk.core import xray_recorder
    from xraysink.context import AsyncContext  # NB: Use the AsyncContext from xraysink
    
    # Use the fixed AsyncContext when configuring X-Ray,
    # and customise other configuration as you choose.
    xray_recorder.configure(context=AsyncContext(use_task_factory=True))


### Background Jobs/Tasks
If your process starts background tasks that make network calls (eg. to the
database or an API in another service), then each execution of one of those
tasks should be treated as a new X-Ray trace. Indeed, if you don't do so then
you will likely get context_missing errors.

An async function that implements a background task can be easily instrumented
using the `@xray_task_async()` decorator, like so:

    from aws_xray_sdk.core import xray_recorder
    from xraysink.tasks import xray_task_async

    # Standard asyncio X-Ray configuration, customise as you choose
    xray_recorder.configure(context=AsyncContext(), service="my-cute-little-service")
    
    # Any call to this function will start a new X-Ray trace
    @xray_task_async()
    async def cleanup_stale_tokens():
        await database.get_table("tokens").delete(age__gt=1)
    
    # Start your background task using your scheduling system of choice :)
    schedule_recurring_task(cleanup_stale_tokens)

If your background task functions are called from a function that is already
instrumented (eg. send an email immediately after handling a request), then 
the background task will appear as a child segment of that trace. In this case,
you must ensure you use the fixed `AsyncContext` when configuring the recorder
(ie. `from xraysink.context import AsyncContext`)


### Process-Level Configuration
You can link your X-Ray traces to your CloudWatch Logs log records, which
enhances the integration with AWS CloudWatch ServiceLens. Take the following
steps:

1.  Put the X-Ray trace ID into every log message. There is no convention for
    how to do this (it just has to appear verbatim in the log message
    somewhere), but if you are using structured logging then the convention is
    to use a field called `traceId`. Here's an example
    
        trace_id = xray_recorder.get_trace_entity().trace_id
        logging.getLogger("example").info("Hello World!", extra={"traceId": trace_id})

1.  Explicitly set the name of the CloudWatch Logs log group associated with
    your process. There is no general way to detect the Log Group from inside
    the process, hence it requires manual configuration as part of your process
    initialisation (eg. in the same place where you call
    `xray_recorder.configure`).
    
        set_xray_log_group("/example/service-name")

Note that this feature relies on undocumented functionality, and is
[not yet](https://github.com/aws/aws-xray-sdk-python/issues/188)
supported by the official Python SDK.


## Licence
This project uses the Apache 2.0 licence, to make it compatible with
[aws_xray_sdk](https://github.com/aws/aws-xray-sdk-python), the
primary library for integrating with AWS X-Ray.
