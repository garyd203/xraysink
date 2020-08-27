# xraysink (aka xray-asyncio)
Extra AWS X-Ray instrumentation to use distributed tracing with asyncio Python
libraries that are not (yet) supported by the official
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


### Process-Level Configuration
You can link your X-Ray traces to your CloudWatch Logs log records, which
enhances the integration with AWS CLoudWatch ServiceLens. Take the following
steps:

1.  Put the X-Ray trace ID into every log message. There is no convention for
    how to do this (it just has to appear verbatim in the log message
    somewhere), but if you are using structured logging then the convention is
    to use a field called `traceId`. Here's an example
    
        trace_id = xray_recorder.get_trace_entity().trace_id
        logging.getLogger("example").info("Hello World!", extra={"traceId": trace_id})

1.  Explicitly set the name of the CloudWatch Logs log group associated with
    your process. There is no general way to detect the Log Group from inside
    the process, hence it requires manual configuration.
    
        set_xray_log_group("/example/service-name")

Note that this feature relies on undocumented functionality, and is
[not yet](https://github.com/aws/aws-xray-sdk-python/issues/188)
supported by the official Python SDK.

## Licence
This project uses the Apache 2.0 licence, to make it compatible with
[aws_xray_sdk](https://github.com/aws/aws-xray-sdk-python), the
primary library for integrating with AWS X-Ray.
