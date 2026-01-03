from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from mersal.messages import TransportMessage
from mersal_polling.plugin import PollingPlugin
from mersal_polling.poller import Poller, ProblemDetails

__all__ = (
    "FailedCompletionCorrelation",
    "PollingConfig",
    "SuccessfulCompletionCorrelation",
)


EventType = TypeVar("EventType")


@dataclass
class SuccessfulCompletionCorrelation(Generic[EventType]):
    """Correlates an event with the successful completion of a message (usually a command).

    The correlation is either based on a custom callback that is given the event
    and should return the message id or by default; the correlation id will be used.

    Args:
        message_id_getter: Callback to extract message ID from the event
        data_builder: Callback to build success data from the event (for rich results)
    """

    message_id_getter: Callable[[EventType], Any] | None = None
    data_builder: Callable[[EventType], dict[str, Any]] | None = None


@dataclass
class FailedCompletionCorrelation(Generic[EventType]):
    """Correlates an event with the failed completion of a message (usually a command).

    The correlation is either based on a custom callback that is given the event
    and should return the message id or by default; the correlation id will be used.

    Args:
        message_id_getter: Callback to extract message ID from the event
        problem_builder: Callback to build RFC 7807 Problem Details for business failures
    """

    message_id_getter: Callable[[EventType], Any] | None = None
    problem_builder: Callable[[EventType], ProblemDetails] | None = None


@dataclass
class PollingConfig:
    """Configuration for the polling functionality.

    Args:
        poller: The poller instance to use
        successful_completion_events_map: Map of event types to successful completion correlations
        failed_completion_events_map: Map of event types to failed completion correlations
        auto_publish_completion_events: Whether to automatically publish message completion events
        exclude_from_completion_events: Message types to exclude from automatic completion events
    """

    poller: Poller
    successful_completion_events_map: dict[type, SuccessfulCompletionCorrelation] = field(default_factory=dict)
    failed_completion_events_map: dict[type, FailedCompletionCorrelation] = field(default_factory=dict)
    auto_publish_completion_events: bool = True
    exclude_from_completion_events: set[type] = field(default_factory=set)
    problem_factory: Callable[[Exception, TransportMessage], ProblemDetails] | None = None

    @property
    def plugin(self) -> PollingPlugin:
        return PollingPlugin(self)
