# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v1.4.0 (2021-12-23)

Fixed:
* Update test code to work with latest versions of everything.

## v1.3.1 (2020-09-28)

Fixed:
* `KeyError: 'entities'` when using custom `AsyncContext`.


## v1.3.0 (2020-09-24)

Changed:
* `@xray_task_async()` can be used for functions that are started from within
  an existing X-Ray segment.


## v1.2.0 (2020-09-22)

Added:
* Custom `AsyncContext` class as a drop-in replacement for the context from
  `aws_xray_sdk` that behaves incorrectly when creating an asyncio task.  


## v1.1.0 (2020-08-27)

Changed:
* `@xray_task_async()` can be used to decorate methods and classmethods.
* `@xray_task_async()` can set the path component of the synthetic URL.

Added:
* `set_xray_log_group()` process-level configuration function (non-async).


## v1.0.0 (2020-08-05)

Changed:
* Handle `remote-addr` header as source of client IP for middleware.

Added:
* `@xray_task_async()` decorator for starting a traced background task.
