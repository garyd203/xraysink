import logging
from unittest.mock import patch

import pytest
from aws_xray_sdk import global_sdk_config
from aws_xray_sdk.core.async_context import AsyncContext
from aws_xray_sdk.core.async_recorder import AsyncAWSXRayRecorder

from .xray_util import get_new_stubbed_recorder


@pytest.fixture
def caplog(caplog):
    """
    Override the standard caplog fixture to have a more sensible default level on the root logger.
    """
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest.fixture
def recorder(event_loop) -> AsyncAWSXRayRecorder:
    """An X-Ray recorder with local-only, stubbed, segment collection."""
    xray_recorder = get_new_stubbed_recorder()
    xray_recorder.configure(
        service="test", sampling=False, context=AsyncContext(loop=event_loop)
    )

    with patch("xraysink.asgi.middleware.xray_recorder", xray_recorder), patch(
        "xraysink.config.xray_recorder", xray_recorder
    ), patch("xraysink.tasks.xray_recorder", xray_recorder), patch(
        "xraysink.util.xray_recorder", xray_recorder
    ):
        xray_recorder.clear_trace_entities()
        yield xray_recorder
        global_sdk_config.set_sdk_enabled(True)
        xray_recorder.clear_trace_entities()
