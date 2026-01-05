import uuid
from typing import Any

from anyio import Event

from .poller import Poller, PollingResult, PollingStatus, ProblemDetails

__all__ = ("DefaultPoller",)


class DefaultPoller(Poller):
    """In-memory implementation of the Poller protocol.

    Suitable for single-server deployments or testing. For multi-server
    deployments, use a distributed poller implementation (e.g., DatabasePoller).
    """

    def __init__(self) -> None:
        self.results: dict[uuid.UUID, PollingResult] = {}
        self.events: dict[uuid.UUID, Event] = {}

    async def poll(
        self,
        message_id: uuid.UUID,
        exclude_statuses: list[PollingStatus] | None = None,
    ) -> PollingResult:
        # Check if result already exists
        message = self.results.get(message_id)
        if message and (not exclude_statuses or message.status not in exclude_statuses):
            return message

        # Create an event for this message_id if it doesn't exist
        if message_id not in self.events:
            self.events[message_id] = Event()

        # Wait for the event to be set and check if it matches the filter
        while True:
            await self.events[message_id].wait()
            message = self.results[message_id]
            if not exclude_statuses or message.status not in exclude_statuses:
                return message
            # Reset the event to wait for the next update
            self.events[message_id] = Event()

    async def peek(
        self,
        message_id: uuid.UUID,
        exclude_statuses: list[PollingStatus] | None = None,
    ) -> PollingResult | None:
        """Check if a result exists without blocking."""
        message = self.results.get(message_id)
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
        # Store the result
        self.results[message_id] = PollingResult(
            message_id=message_id,
            status=status,
            data=data,
            problem=problem,
        )

        # If there's a waiting event, trigger it
        if message_id in self.events:
            self.events[message_id].set()
