from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from mersal.messages.message_completed_event import MessageCompletedEvent

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mersal.activation import HandlerActivator
    from mersal.app import Mersal
    from mersal.pipeline import MessageContext
    from mersal.types import AsyncAnyCallable

__all__ = (
    "REPLY_TO_HEADER",
    "message_completion_event_publisher",
    "register_message_completion_publishers",
)

REPLY_TO_HEADER = "reply_to"


def message_completion_event_publisher(
    message_context: MessageContext,
    app: Mersal,
    _: list[AsyncAnyCallable],
) -> Callable[[Any], Awaitable[None]]:
    """Create a handler that publishes a MessageCompletedEvent.

    This function creates a message handler that publishes a MessageCompletedEvent
    when invoked, allowing for tracking message processing completion.

    If the incoming message carries a ``reply_to`` header, the completion event
    is sent directly to that address instead of being broadcast to all
    subscribers, avoiding unnecessary fan-out across unrelated apps.

    Args:
        message_context: The message context for the current message
        app: The Mersal application instance
        _: Unused parameter for compatibility with handler factory signature

    Returns:
        A message handler function that publishes a completion event
    """

    async def handler(_: Any) -> None:
        completed_message_id = message_context.headers.message_id
        published_message_id = uuid.uuid4()
        event = MessageCompletedEvent(completed_message_id=completed_message_id)
        event_headers = {"message_id": published_message_id}

        reply_to = message_context.headers.get(REPLY_TO_HEADER)
        if reply_to:
            await app.send(event, headers=event_headers, addresses={reply_to})

    return handler


def register_message_completion_publishers(
    activator: HandlerActivator,
    exclude_types: set[type] | None = None,
) -> None:
    """Register message completion event publishers for all message types.

    This function registers handlers that publish MessageCompletedEvent for all
    message types that already have handlers registered in the activator, except
    for those in the exclude_types set.

    Args:
        activator: The handler activator to register completion publishers with
        exclude_types: Message types to exclude from completion event publishing
    """
    # Create exclude set (always exclude MessageCompletedEvent itself)
    exclude: set[type] = set() if exclude_types is None else exclude_types.copy()
    exclude.add(MessageCompletedEvent)

    # Get all registered message types
    completion_event_registry: set[type] = set()

    # Register completion event publishers for all message types
    for message_type in activator.registered_message_types:
        if message_type not in exclude and message_type not in completion_event_registry:
            # For each message type, register a handler that publishes completion events
            def completion_publisher_factory(
                message_context: MessageContext,
                app: Mersal,
            ) -> Callable[[Any], Awaitable[None]]:
                return message_completion_event_publisher(
                    message_context=message_context,
                    app=app,
                    _=[],
                )

            activator.register(message_type, completion_publisher_factory)
            completion_event_registry.add(message_type)
