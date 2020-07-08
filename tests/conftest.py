import logging

import pytest


@pytest.fixture
def caplog(caplog):
    """Override the standard caplog fixture to provide a more sensible default level on the root logger."""
    caplog.set_level(logging.DEBUG)
    return caplog
