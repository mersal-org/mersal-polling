"""Testing utilities for mersal_polling.

This module provides test doubles and utilities for testing code that uses polling.
"""

import uuid
from typing import Any

from .poller import Poller, PollingResult, PollingStatus, ProblemDetails

__all__ = ("PollerTestDouble",)


class PollerTestDouble(Poller):
    """A test double that combines stubbing and spying capabilities.

    This test double allows you to:
    1. Stub results by pre-configuring what poll() should return
    2. Spy on all interactions to make assertions

    Example - Stubbing Success:
        >>> poller = PollerTestDouble()
        >>> message_id = uuid.uuid4()
        >>>
        >>> # Pre-configure a successful result
        >>> poller.stub_success(message_id, data={"batch_id": "123", "succeeded": 100, "failed": 5})
        >>>
        >>> result = await poller.poll(message_id)
        >>> assert result.is_success
        >>> assert result.data["succeeded"] == 100

    Example - Stubbing Failure:
        >>> poller = PollerTestDouble()
        >>> message_id = uuid.uuid4()
        >>>
        >>> # Pre-configure a failure result
        >>> poller.stub_failure(
        ...     message_id,
        ...     problem=ProblemDetails(
        ...         type="https://api.example.com/problems/insufficient-funds",
        ...         title="Insufficient Funds",
        ...         status=400,
        ...     ),
        ... )
        >>>
        >>> result = await poller.poll(message_id)
        >>> assert result.is_failure
        >>> assert result.problem.status == 400

    Example - Spying:
        >>> poller = PollerTestDouble()
        >>>
        >>> # Use in your code
        >>> await poller.push(message_id, data={"result": "ok"})
        >>>
        >>> # Make assertions
        >>> assert poller.push_count == 1
        >>> assert poller.last_push["data"] == {"result": "ok"}

    Example - Combined:
        >>> poller = PollerTestDouble()
        >>> message_id = uuid.uuid4()
        >>>
        >>> # Stub what poll should return
        >>> poller.stub_result(message_id, data={"status": "complete"})
        >>>
        >>> # Use it
        >>> result = await poller.poll(message_id)
        >>>
        >>> # Verify interactions
        >>> assert poller.poll_count == 1
        >>> assert poller.last_poll_message_id == message_id
    """

    def __init__(self) -> None:
        # Storage for stubbed results
        self._stubbed_results: dict[uuid.UUID, PollingResult] = {}

        # Spy counters
        self.poll_count: int = 0
        self.peek_count: int = 0
        self.push_count: int = 0

        # Last call tracking
        self.last_poll_message_id: uuid.UUID | None = None
        self.last_peek_message_id: uuid.UUID | None = None
        self.last_push: dict[str, Any] | None = None

        # All calls tracking
        self.all_poll_calls: list[uuid.UUID] = []
        self.all_peek_calls: list[uuid.UUID] = []
        self.all_push_calls: list[dict[str, Any]] = []

    def stub_result(
        self,
        message_id: uuid.UUID,
        status: PollingStatus = "succeeded",
        data: dict[str, Any] | None = None,
        problem: ProblemDetails | None = None,
    ) -> None:
        """Pre-configure a result that poll() or peek() should return.

        Args:
            message_id: The message ID to stub the result for
            status: The status of the operation (accepted, succeeded, failed)
            data: Optional success data
            problem: Optional Problem Details for failures
        """
        self._stubbed_results[message_id] = PollingResult(
            message_id=message_id,
            status=status,
            data=data,
            problem=problem,
        )

    def stub_accepted(self, message_id: uuid.UUID, data: dict[str, Any] | None = None) -> None:
        """Convenience method to stub an accepted result (HTTP 202 semantics).

        Args:
            message_id: The message ID
            data: Optional acceptance data
        """
        self.stub_result(message_id, status="accepted", data=data)

    def stub_success(self, message_id: uuid.UUID, data: dict[str, Any] | None = None) -> None:
        """Convenience method to stub a successful result.

        Args:
            message_id: The message ID
            data: Optional success data
        """
        self.stub_result(message_id, data=data)

    def stub_failure(
        self,
        message_id: uuid.UUID,
        problem: ProblemDetails,
    ) -> None:
        """Convenience method to stub a failure result.

        Args:
            message_id: The message ID
            problem: Problem Details describing the failure
        """
        self.stub_result(message_id, status="failed", problem=problem)

    async def poll(
        self,
        message_id: uuid.UUID,
        exclude_statuses: list[PollingStatus] | None = None,
    ) -> PollingResult:
        """Return the stubbed result and record the call.

        Args:
            message_id: The message ID to poll for
            exclude_statuses: Optional list of statuses to exclude from results

        Returns:
            The stubbed polling result

        Raises:
            KeyError: If no result was stubbed for this message ID
        """
        self.poll_count += 1
        self.last_poll_message_id = message_id
        self.all_poll_calls.append(message_id)

        if message_id not in self._stubbed_results:
            raise KeyError(
                f"No result stubbed for message {message_id}. "
                f"Use stub_result() or stub_success()/stub_failure() to configure expected results."
            )

        message = self._stubbed_results[message_id]
        if exclude_statuses and message.status in exclude_statuses:
            raise KeyError(
                f"Result for message {message_id} has status '{message.status}' "
                f"which is in the excluded statuses list: {exclude_statuses}"
            )
        return message

    async def peek(
        self,
        message_id: uuid.UUID,
        exclude_statuses: list[PollingStatus] | None = None,
    ) -> PollingResult | None:
        """Return the stubbed result if available and record the call.

        Args:
            message_id: The message ID to check
            exclude_statuses: Optional list of statuses to exclude from results

        Returns:
            The stubbed result if configured, None otherwise
        """
        self.peek_count += 1
        self.last_peek_message_id = message_id
        self.all_peek_calls.append(message_id)

        message = self._stubbed_results.get(message_id)
        if message and exclude_statuses and message.status in exclude_statuses:
            return None
        return message

    async def push(
        self,
        message_id: uuid.UUID,
        status: PollingStatus = "succeeded",
        data: dict[str, Any] | None = None,
        problem: ProblemDetails | None = None,
    ) -> None:
        """Store the result and record the call.

        Args:
            message_id: The message ID
            status: The status of the operation (accepted, succeeded, failed)
            data: Optional success data
            problem: Optional Problem Details
        """
        self.push_count += 1
        call_info = {
            "message_id": message_id,
            "status": status,
            "data": data,
            "problem": problem,
        }
        self.last_push = call_info
        self.all_push_calls.append(call_info)

        # Also store as a stubbed result so peek/poll can retrieve it
        self.stub_result(message_id, status, data, problem)

    def reset(self) -> None:
        """Reset all stubbed results and recorded calls."""
        self._stubbed_results.clear()
        self.poll_count = 0
        self.peek_count = 0
        self.push_count = 0
        self.last_poll_message_id = None
        self.last_peek_message_id = None
        self.last_push = None
        self.all_poll_calls.clear()
        self.all_peek_calls.clear()
        self.all_push_calls.clear()

    def was_polled(self, message_id: uuid.UUID) -> bool:
        """Check if a specific message ID was polled.

        Args:
            message_id: The message ID to check

        Returns:
            True if the message was polled at least once
        """
        return message_id in self.all_poll_calls

    def was_pushed(self, message_id: uuid.UUID) -> bool:
        """Check if a result was pushed for a specific message ID.

        Args:
            message_id: The message ID to check

        Returns:
            True if a result was pushed for this message at least once
        """
        return any(call["message_id"] == message_id for call in self.all_push_calls)
