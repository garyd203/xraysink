# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).



## v1.1.0 (UNRELEASED)

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
