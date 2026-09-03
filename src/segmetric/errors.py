class SegMetricError(Exception):
    """A processing failure with a message safe to show directly to a researcher.

    Never wraps a raw traceback in the message text -- callers should log the
    original exception separately for developer-facing debugging.
    """
