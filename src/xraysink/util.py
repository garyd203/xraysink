"""Miscellaneous functions for working with the X-Ray SDK."""

from aws_xray_sdk.core import xray_recorder


# noinspection PyProtectedMember
def has_current_trace() -> bool:
    """Whether there is currently a trace.

    This is like calling xray_recorder.get_trace_entity(), but without the
    annoying error handling.
    """
    # See authoritative implementation in aws_xray_sdk.core.context.Context.get_trace_entity()
    return bool(getattr(xray_recorder.context._local, "entities", None))
