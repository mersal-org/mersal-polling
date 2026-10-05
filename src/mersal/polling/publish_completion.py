from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mersal.messages import LogicalMessage
from mersal.pipeline import IncomingStepContext
from mersal.polling.message_completion_handler import REPLY_TO_HEADER
from mersal.polling.poller import TransactionalPoller
from mersal.transport import TransactionContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from mersal.pipeline import MessageContext, OutgoingStepContext
    from mersal.polling.config import (
        AcceptedCorrelation,
        FailedCompletionCorrelation,
        SuccessfulCompletionCorrelation,
    )
    from mersal.polling.poller import Poller, PollingStatus, ProblemDetails
    from mersal.types import AsyncAnyCallable

__all__ = (
    "PollingResultRecorder",
    "PublishCompletionStep",
    "message_completion_recorder",
)


class PollingResultRecorder:
    """Records a polling result from within a message's processing - the
    `complete_on="publish"` counterpart of pushing when a correlated event is received.
    """

    def __init__(self, poller: Poller) -> None:
        self._poller = poller

    async def record(
        self,
        transaction_context: TransactionContext,
        message_id: Any,
        status: PollingStatus,
        data: dict[str, Any] | None = None,
        problem: ProblemDetails | None = None,
    ) -> None:
        message_id = str(message_id)
        poller = self._poller
        handling_a_message = transaction_context.items.get(IncomingStepContext.step_context_key) is not None
        if (
            handling_a_message
            and isinstance(poller, TransactionalPoller)
            and poller.can_push_in_transaction(transaction_context)
        ):
            # Written now but committed (or rolled back) with the handler's own work.
            await poller.push_in_transaction(transaction_context, message_id, status, data, problem)
            return

        committed = False

        async def mark_committed(_: TransactionContext) -> None:
            nonlocal committed
            committed = True

        async def push(_: TransactionContext) -> None:
            if committed:
                await poller.push(message_id, status, data, problem)

        # Ack actions run only once every commit action has succeeded - including a
        # unit of work's commit, which is registered after the handler returns, so
        # after anything registered here as a commit action would run. A message
        # given up on is acked without committing though, hence the commit check.
        transaction_context.on_commit(mark_committed)
        transaction_context.on_ack(push)


class PublishCompletionStep:
    """Outgoing step recording a polling result when a correlated event is sent."""

    def __init__(
        self,
        recorder: PollingResultRecorder,
        accepted_events_map: Mapping[type, AcceptedCorrelation],
        successful_completion_events_map: Mapping[type, SuccessfulCompletionCorrelation],
        failed_completion_events_map: Mapping[type, FailedCompletionCorrelation],
    ) -> None:
        self._recorder = recorder
        self._accepted_events_map = accepted_events_map
        self._successful_completion_events_map = successful_completion_events_map
        self._failed_completion_events_map = failed_completion_events_map

    async def __call__(self, context: OutgoingStepContext, next_step: AsyncAnyCallable) -> None:
        logical_message = context.load(LogicalMessage)
        await next_step()

        event = logical_message.body
        # By the MRO, like the handler activator dispatching a received event would.
        for event_type in type(event).__mro__:
            correlation: AcceptedCorrelation | SuccessfulCompletionCorrelation | FailedCompletionCorrelation | None = (
                None
            )

            if correlation := self._accepted_events_map.get(event_type):
                status: PollingStatus = "accepted"
                data = correlation.data_builder(event) if correlation.data_builder else None
                problem = None
            elif correlation := self._successful_completion_events_map.get(event_type):
                status = "succeeded"
                data = correlation.data_builder(event) if correlation.data_builder else None
                problem = None
            elif correlation := self._failed_completion_events_map.get(event_type):
                status = "failed"
                data = None
                problem = correlation.problem_builder(event) if correlation.problem_builder else None
            else:
                continue

            if correlation.message_id_getter:
                message_id = correlation.message_id_getter(event)
            else:
                # Set by `FlowCorrelationStep` from the message being handled.
                message_id = logical_message.headers.correlation_id
            if message_id is None:
                return

            transaction_context = context.load(TransactionContext)  # type: ignore[type-abstract]
            await self._recorder.record(transaction_context, message_id, status, data=data, problem=problem)
            return


def message_completion_recorder(
    message_context: MessageContext,
    recorder: PollingResultRecorder,
) -> Callable[[Any], Awaitable[None]]:
    """The `complete_on="publish"` counterpart of `message_completion_event_publisher`:
    records the handled message as succeeded instead of sending a
    `MessageCompletedEvent` to its ``reply_to`` address. Like the publisher, it only
    does so for messages carrying a ``reply_to`` header - someone waiting on them.
    """

    async def handler(_: Any) -> None:
        if not message_context.headers.get(REPLY_TO_HEADER):
            return
        completed_message_id = message_context.headers.message_id
        if completed_message_id is None:
            raise RuntimeError("Received message has no message id set.")
        await recorder.record(message_context.transaction_context, completed_message_id, "succeeded")

    return handler
