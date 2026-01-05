from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

__all__ = (
    "Poller",
    "PollingResult",
    "PollingStatus",
    "ProblemDetails",
)

PollingStatus = Literal["accepted", "completed", "failed"]


@dataclass
class ProblemDetails:
    """RFC 7807 Problem Details for HTTP APIs.

    Provides a standardized way to carry machine-readable details of errors
    in HTTP response bodies.

    Args:
        type: A URI reference that identifies the problem type
        title: A short, human-readable summary of the problem type
        status: The HTTP status code
        detail: A human-readable explanation specific to this occurrence
        instance: A URI reference that identifies the specific occurrence
        extensions: Additional custom fields for problem-specific data
    """

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)


@dataclass
class PollingResult:
    """Result of polling for a message completion.

    Args:
        message_id: The ID of the message being polled
        status: The status of the operation (accepted, completed, failed)
        data: Success data (for batch operations, rich results, etc.)
        problem: Structured error information (RFC 7807) for any failure
    """

    message_id: Any
    status: PollingStatus = "completed"
    data: dict[str, Any] | None = None
    problem: ProblemDetails | None = None

    @property
    def is_accepted(self) -> bool:
        """Returns True if the operation has been accepted for processing."""
        return self.status == "accepted"

    @property
    def is_success(self) -> bool:
        """Returns True if the operation completed successfully."""
        return self.status == "completed" and self.problem is None

    @property
    def is_failure(self) -> bool:
        """Returns True if the operation failed."""
        return self.status == "failed" or self.problem is not None


class Poller(Protocol):
    """Protocol for polling message completion results.

    Implementations can be in-memory (DefaultPoller) or distributed (DatabasePoller).
    """

    async def poll(self, message_id: Any) -> PollingResult:
        """Wait for and return the result of a message processing.

        This method blocks until the result is available.

        Args:
            message_id: The ID of the message to poll for

        Returns:
            The polling result
        """
        ...

    async def peek(self, message_id: Any) -> PollingResult | None:
        """Check if a result exists without blocking.

        This method returns immediately, either with a result or None.
        Useful for client-side polling scenarios.

        Args:
            message_id: The ID of the message to check

        Returns:
            The polling result if available, None otherwise
        """
        ...

    async def push(
        self,
        message_id: Any,
        status: PollingStatus = "completed",
        data: dict[str, Any] | None = None,
        problem: ProblemDetails | None = None,
    ) -> None:
        """Store the result of a message processing.

        Args:
            message_id: The ID of the message
            status: The status of the operation (accepted, completed, failed)
            data: Success data (for rich results, batch operations)
            problem: Structured error information (RFC 7807) for failures
        """
        ...
