# xraysink (aka xray-asyncio)
Extra AWS X-Ray instrumentation for asyncio Python libraries that are not
(yet) supported by the official
[aws_xray_sdk](https://github.com/aws/aws-xray-sdk-python)
library.


## Integrations Supported
* Generic ASGI-compatible tracing middleware for *any* ASGI-compliant web
  framework. This has been tested with:
  - [aiohttp](https://docs.aiohttp.org/en/stable/)
  - [fastapi](https://fastapi.tiangolo.com/)


## Licence
This project uses the Apache 2.0 licence, to make it compatible with
[aws_xray_sdk](https://github.com/aws/aws-xray-sdk-python), the
primary library for integrating with AWS X-Ray.
