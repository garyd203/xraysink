"""Tests for configuration tools"""

import pytest

from xraysink.config import set_xray_log_group

pytestmark = pytest.mark.asyncio


class TestSetXrayLogGroup:
    """Tests for set_xray_log_group()"""

    async def test_should_set_log_group_in_segment(self, recorder):
        # Setup
        log_group = "/my/log/group"
        set_xray_log_group(log_group)

        # Exercise
        async with recorder.in_segment_async():
            pass

        # Verify
        segment = recorder.emitter.pop()

        log_data = segment.aws["cloudwatch_logs"]
        assert log_data["log_group"] == log_group
