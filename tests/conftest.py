import logging
from unittest.mock import patch

import pytest
from aws_xray_sdk import global_sdk_config
from aws_xray_sdk.core.async_context import AsyncContext

from xray_util import get_new_stubbed_recorder


@pytest.fixture
def caplog(caplog):
    """Override the standard caplog fixture to provide a more sensible default level on the root logger."""
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture(scope="function")
def recorder(event_loop):
    """
    Clean up context storage before and after each test run
    """
    xray_recorder = get_new_stubbed_recorder()
    xray_recorder.configure(
        service="test", sampling=False, context=AsyncContext(loop=event_loop)
    )

    patcher = patch("xraysink.asgi.middleware.xray_recorder", xray_recorder)
    patcher.start()

    xray_recorder.clear_trace_entities()
    yield xray_recorder
    global_sdk_config.set_sdk_enabled(True)
    xray_recorder.clear_trace_entities()
    patcher.stop()
