import uuid
from typing import Any

from anyio import fail_after

from mersal.exceptions import MersalExceptionError

from .poller import Poller, PollingResult, PollingStatus, ProblemDetails

__all__ = (
    "PollerWithTimeout",
    "PollingTimeoutError",
)


class PollingTimeoutError(MersalExceptionError):
    pass


class PollerWithTimeout(Poller):
    """Wrapper that adds timeout support to any Poller implementation."""

    def __init__(self, poller: Poller) -> None:
        self._poller = poller

    async def poll(self, message_id: uuid.UUID, timeout: float = 30) -> PollingResult:
        try:
            with fail_after(timeout):
                return await self._poller.poll(message_id)
        except TimeoutError as e:
            raise PollingTimeoutError() from e

    async def peek(self, message_id: uuid.UUID) -> PollingResult | None:
        """Delegate peek to underlying poller (no timeout needed for non-blocking operation)."""
        return await self._poller.peek(message_id)

    async def push(
        self,
        message_id: uuid.UUID,
        status: PollingStatus = "completed",
        data: dict[str, Any] | None = None,
        problem: ProblemDetails | None = None,
    ) -> None:
        """Delegate push to underlying poller."""
        await self._poller.push(message_id, status, data, problem)
