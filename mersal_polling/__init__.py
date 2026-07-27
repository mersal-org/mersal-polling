from importlib.metadata import version

from .config import (
    AcceptedCorrelation,
    FailedCompletionCorrelation,
    PollingConfig,
    SuccessfulCompletionCorrelation,
)
from .default_poller import DefaultPoller
from .message_completion_handler import (
    REPLY_TO_HEADER,
    message_completion_event_publisher,
    register_message_completion_publishers,
)
from .poller import Poller, PollingResult, PollingStatus, ProblemDetails
from .poller_with_timeout import PollerWithTimeout, PollingTimeoutError
from .testing import PollerTestDouble

__all__ = [
    "REPLY_TO_HEADER",
    "AcceptedCorrelation",
    "DefaultPoller",
    "FailedCompletionCorrelation",
    "Poller",
    "PollerTestDouble",
    "PollerWithTimeout",
    "PollingConfig",
    "PollingResult",
    "PollingStatus",
    "PollingTimeoutError",
    "ProblemDetails",
    "SuccessfulCompletionCorrelation",
    "message_completion_event_publisher",
    "register_message_completion_publishers",
]


def __getattr__(name: str) -> str:
    if name != "__version__":
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)

    return version("mersal_polling")
