"""Errors raised at the optional DSP worker boundary."""


class WorkerUnavailableError(RuntimeError):
    """The optional worker runtime or its endpoint is unavailable."""


class WorkerProtocolError(RuntimeError):
    """The worker returned a malformed or mismatched message."""


class WorkerTimeoutError(TimeoutError):
    """The worker did not reply before the configured timeout."""


class WorkerExecutionError(RuntimeError):
    """The worker reported an error while running a codec operation."""
