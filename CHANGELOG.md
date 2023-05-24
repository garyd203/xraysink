# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## v1.7.0 (unreleased)

Changed:
* Test against `aws_xray_sdk` release up to v2.12.0
* Test functionality in `AsyncContext` in `aws_xray_sdk`, including fix in v2.10.0


## v1.6.1 (2023-03-06)

Changed:
* Test support for python v3.11 and upgrade some dependencies. No code changes.


## v1.6.0 (2022-05-18)

Changed:
* Removed explicit support for Python 3.6. Releases of `xraysink` are no longer tested
  against Python 3.6, and are not marked as compatible with Python 3.6 for `poetry`/`pip`.


## v1.5.2 (2022-05-10)

Changed:
* Fallback to "localhost" in middleware if the `Host` header is not supplied.
  (h/t @mroswald)


## v1.5.1 (2022-03-12)

Changed:
* Updated minimum supported Python version from v3.6.0 to v3.6.2. This was
  caused by updating the minimum versions of the libraries we test against.


## v1.5.0 (cancelled release)

Release was cancelled due to issues with CI and publishing. See v1.5.1 instead.


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
