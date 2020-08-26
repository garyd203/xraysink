"""Additional tools for configuring X-Ray in a Python process"""

from aws_xray_sdk.core import xray_recorder


def set_xray_log_group(log_group: str):
    """Set the CloudWatch Logs log group used by this process.

    The log group is used in AWS ServiceLens to help link a trace with the
    related log records. The caller is still responsible for putting the
    trace ID into every log record (there is no standard, it simply needs to
    appear verbatim somewhere in the log message, whether structured or
    unstructured)

    This function interacts with the AWS segment metadata that is set by the
    SDK plugins. This means that if you reset the plugin data (by setting the
    plugins to `()`), then the log group will be reset also. It also means
    that if any plugin also sets the log group, then the most recently set
    value will persist.
    """
    log_resources = xray_recorder._aws_metadata.setdefault("cloudwatch_logs", {})
    log_resources["log_group"] = log_group
