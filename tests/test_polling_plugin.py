import uuid
from dataclasses import dataclass
from typing import Any

import anyio
import pytest

from mersal.activation import (
    BuiltinHandlerActivator,
)
from mersal.app import Mersal
from mersal.lifespan.autosubscribe import AutosubscribeConfig
from mersal.messages import MessageCompletedEvent
from mersal.persistence.in_memory import (
    InMemorySubscriptionStorage,
)
from mersal.pipeline import MessageContext
from mersal.serialization.serializers import Serializer
from mersal.transport.in_memory import InMemoryTransport
from mersal_polling import (
    DefaultPoller,
    PollerWithTimeout,
    PollingConfig,
    PollingTimeoutError,
    ProblemDetails,
)
from mersal_polling.config import (
    AcceptedCorrelation,
    FailedCompletionCorrelation,
    SuccessfulCompletionCorrelation,
)
from mersal_testing.message_handlers.message_handler_that_counts import MessageHandlerThatCounts

__all__ = (
    "Message1",
    "Message1CompletedSuccessfully",
    "Message1FailedToComplete",
    "MessageHandler",
    "MessageHandlerThatPublishes",
    "SlowHandler",
    "TestPollingPlugin",
    "ThrowingMessageHandler",
)


pytestmark = pytest.mark.anyio


class Message1:
    pass


class Message2:
    pass


@dataclass
class Message1CompletedSuccessfully:
    pass


@dataclass
class Message2CompletedSuccessfully:
    pass


@dataclass
class Message1FailedToComplete:
    pass


@dataclass
class Message2FailedToComplete:
    pass


@dataclass
class Message1Accepted:
    pass


@dataclass
class Message2Accepted:
    pass


class MessageHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, message: Any):
        self.calls += 1


class SlowHandler:
    def __init__(self, delay: int) -> None:
        self.calls = 0
        self.delay = delay

    async def __call__(self, message: Any):
        self.calls += 1
        await anyio.sleep(self.delay)


class ThrowingMessageHandler:
    async def __call__(self, message: Any):
        raise Exception()


class MessageHandlerThatPublishes:
    def __init__(self, message_context: MessageContext, app: Mersal, published_message: Any) -> None:
        self.calls = 0
        self.app = app
        self.message_context = message_context
        self.published_message = published_message

    async def __call__(self, message: Any):
        self.calls += 1
        await self.app.publish(self.published_message)


class TestPollingPlugin:
    async def test_polling(
        self,
        in_memory_transport: InMemoryTransport,
        in_memory_subscription_storage: InMemorySubscriptionStorage,
        serializer: Serializer,
    ):
        activator = BuiltinHandlerActivator()
        poller = DefaultPoller()
        message_handler = MessageHandlerThatCounts()
        completion_event_handler = MessageHandlerThatCounts()
        activator.register(Message1, lambda __, _: message_handler)
        activator.register(MessageCompletedEvent, lambda _, __: completion_event_handler)
        message1_id = uuid.uuid4()

        app = Mersal(
            "m1",
            activator,
            transport=in_memory_transport,
            serializer=serializer,
            subscription_storage=in_memory_subscription_storage,
            autosubscribe=AutosubscribeConfig(set()),
            plugins=[
                PollingConfig(
                    poller,
                    auto_publish_completion_events=True,
                ).plugin
            ],
        )
        await app.start()

        await anyio.sleep(0.5)

        await app.send_local(Message1(), headers={"message_id": message1_id})

        await anyio.sleep(0.5)

        assert message_handler.count == 1
        assert completion_event_handler.count == 1
        assert isinstance(completion_event_handler.message, MessageCompletedEvent)
        assert completion_event_handler.message.completed_message_id == message1_id

        result = await poller.poll(message1_id)
        assert result
        assert result.is_success

        await app.send_local(Message1(), headers={"message_id": uuid.uuid4()})
        await anyio.sleep(0.5)
        assert message_handler.count == 2
        assert completion_event_handler.count == 2

        await app.stop()

    async def test_polling_with_custom_success_completion_event(
        self,
        in_memory_transport: InMemoryTransport,
        in_memory_subscription_storage: InMemorySubscriptionStorage,
        serializer: Serializer,
    ):
        activator = BuiltinHandlerActivator()
        poller = DefaultPoller()
        app = Mersal(
            "m1",
            activator,
            transport=in_memory_transport,
            serializer=serializer,
            subscription_storage=in_memory_subscription_storage,
            autosubscribe=AutosubscribeConfig(set()),
            plugins=[
                PollingConfig(
                    poller,
                    successful_completion_events_map={
                        Message1CompletedSuccessfully: SuccessfulCompletionCorrelation(),
                        Message2CompletedSuccessfully: SuccessfulCompletionCorrelation(),
                    },
                    exclude_from_completion_events={
                        Message1,
                        Message2,
                    },
                ).plugin
            ],
        )
        activator.register(
            Message1,
            lambda m, b: MessageHandlerThatPublishes(m, b, Message1CompletedSuccessfully()),
        )
        activator.register(
            Message2,
            lambda m, b: MessageHandlerThatPublishes(m, b, Message2CompletedSuccessfully()),
        )
        message1_id = uuid.uuid4()
        message2_id = uuid.uuid4()
        await app.start()

        await app.send_local(Message1(), headers={"message_id": message1_id})
        await app.send_local(Message2(), headers={"message_id": message2_id})
        await anyio.sleep(0.5)
        result1 = await poller.poll(message1_id)
        result2 = await poller.poll(message2_id)
        assert result1
        assert result1.is_success
        assert result2
        assert result2.is_success

        await app.stop()

    async def test_polling_with_custom_failure_completion_event(
        self,
        in_memory_transport: InMemoryTransport,
        in_memory_subscription_storage: InMemorySubscriptionStorage,
        serializer: Serializer,
    ):
        activator = BuiltinHandlerActivator()
        poller = DefaultPoller()
        app = Mersal(
            "m1",
            activator,
            transport=in_memory_transport,
            serializer=serializer,
            subscription_storage=in_memory_subscription_storage,
            autosubscribe=AutosubscribeConfig(set()),
            plugins=[
                PollingConfig(
                    poller,
                    failed_completion_events_map={
                        Message1FailedToComplete: FailedCompletionCorrelation(
                            problem_builder=lambda event: ProblemDetails(
                                type="https://api.example.com/problems/message1-failed",
                                title="Message1 Failed",
                                status=400,
                                detail="Message1 failed to complete",
                            )
                        ),
                        Message2FailedToComplete: FailedCompletionCorrelation(
                            problem_builder=lambda event: ProblemDetails(
                                type="https://api.example.com/problems/message2-failed",
                                title="Message2 Failed",
                                status=422,
                                detail="Message2 failed to complete",
                            )
                        ),
                    },
                    exclude_from_completion_events={
                        Message1,
                        Message2,
                    },
                ).plugin
            ],
        )
        activator.register(
            Message1,
            lambda m, b: MessageHandlerThatPublishes(m, b, Message1FailedToComplete()),
        )
        activator.register(
            Message2,
            lambda m, b: MessageHandlerThatPublishes(m, b, Message2FailedToComplete()),
        )
        message1_id = uuid.uuid4()
        message2_id = uuid.uuid4()
        await app.start()

        await app.send_local(Message1(), headers={"message_id": message1_id})
        await app.send_local(Message2(), headers={"message_id": message2_id})
        await anyio.sleep(0.5)

        result1 = await poller.poll(message1_id)
        result2 = await poller.poll(message2_id)

        assert result1
        assert result1.is_failure
        assert result1.problem is not None
        assert result1.problem.status == 400
        assert result1.problem.title == "Message1 Failed"

        assert result2
        assert result2.is_failure
        assert result2.problem is not None
        assert result2.problem.status == 422
        assert result2.problem.title == "Message2 Failed"

        await app.stop()

    async def test_polling_with_exception(
        self,
        in_memory_transport: InMemoryTransport,
        in_memory_subscription_storage: InMemorySubscriptionStorage,
        serializer: Serializer,
    ):
        activator = BuiltinHandlerActivator()
        poller = DefaultPoller()
        app = Mersal(
            "m1",
            activator,
            transport=in_memory_transport,
            serializer=serializer,
            subscription_storage=in_memory_subscription_storage,
            autosubscribe=AutosubscribeConfig(set()),
            plugins=[PollingConfig(poller).plugin],
        )

        handler = ThrowingMessageHandler()
        activator.register(Message1, lambda __, _: handler)
        message_id = uuid.uuid4()
        await app.start()

        await app.send_local(Message1(), headers={"message_id": message_id})
        await anyio.sleep(0.1)
        result = await poller.poll(message_id)
        assert result
        assert result.is_failure
        assert result.problem is not None
        assert result.problem.status == 500

        await app.stop()

    async def test_polling_with_timeout(
        self,
        in_memory_transport: InMemoryTransport,
        in_memory_subscription_storage: InMemorySubscriptionStorage,
        serializer: Serializer,
    ):
        activator = BuiltinHandlerActivator()
        _poller = DefaultPoller()
        poller = PollerWithTimeout(_poller)
        app = Mersal(
            "m1",
            activator,
            transport=in_memory_transport,
            serializer=serializer,
            subscription_storage=in_memory_subscription_storage,
            autosubscribe=AutosubscribeConfig(set()),
            plugins=[PollingConfig(_poller).plugin],
        )

        handler = SlowHandler(1)
        activator.register(Message1, lambda __, _: handler)
        message_id = uuid.uuid4()
        await app.start()

        await app.send_local(Message1(), headers={"message_id": message_id})
        with pytest.raises(PollingTimeoutError):
            await poller.poll(message_id, timeout=0.5)

        await app.stop()

    async def test_auto_completion_event_with_polling_plugin_excluded(
        self,
        in_memory_transport: InMemoryTransport,
        in_memory_subscription_storage: InMemorySubscriptionStorage,
        serializer: Serializer,
    ):
        activator = BuiltinHandlerActivator()
        message = Message1()

        completion_event_handler = MessageHandlerThatCounts()
        activator.register(MessageCompletedEvent, lambda _, __: completion_event_handler)

        message_handler = MessageHandlerThatCounts()
        activator.register(Message1, lambda m, b: message_handler)

        poller = DefaultPoller()

        plugins = [
            PollingConfig(
                poller,
                auto_publish_completion_events=True,
                exclude_from_completion_events={Message1},
            ).plugin,
        ]

        app = Mersal(
            "m1",
            activator,
            transport=in_memory_transport,
            serializer=serializer,
            subscription_storage=in_memory_subscription_storage,
            plugins=plugins,
        )

        await app.start()

        message_id = uuid.uuid4()
        await app.send_local(message, headers={"message_id": message_id})

        await anyio.sleep(0.1)
        await app.stop()

        assert message_handler.count == 1
        assert completion_event_handler.count == 0

        _poller = PollerWithTimeout(poller)
        with pytest.raises(PollingTimeoutError):
            _ = await _poller.poll(message_id, 1)

    async def test_polling_with_accepted_events(
        self,
        in_memory_transport: InMemoryTransport,
        in_memory_subscription_storage: InMemorySubscriptionStorage,
        serializer: Serializer,
    ):
        activator = BuiltinHandlerActivator()
        poller = DefaultPoller()
        app = Mersal(
            "m1",
            activator,
            transport=in_memory_transport,
            serializer=serializer,
            subscription_storage=in_memory_subscription_storage,
            autosubscribe=AutosubscribeConfig(set()),
            plugins=[
                PollingConfig(
                    poller,
                    accepted_events_map={
                        Message1Accepted: AcceptedCorrelation(),
                        Message2Accepted: AcceptedCorrelation(),
                    },
                    successful_completion_events_map={
                        Message1CompletedSuccessfully: SuccessfulCompletionCorrelation(),
                        Message2CompletedSuccessfully: SuccessfulCompletionCorrelation(),
                    },
                    exclude_from_completion_events={
                        Message1,
                        Message2,
                    },
                ).plugin
            ],
        )
        activator.register(
            Message1,
            lambda m, b: MessageHandlerThatPublishes(m, b, Message1Accepted()),
        )
        activator.register(
            Message2,
            lambda m, b: MessageHandlerThatPublishes(m, b, Message2Accepted()),
        )
        message1_id = uuid.uuid4()
        message2_id = uuid.uuid4()
        await app.start()

        await app.send_local(Message1(), headers={"message_id": message1_id})
        await app.send_local(Message2(), headers={"message_id": message2_id})
        await anyio.sleep(0.5)

        # Poll for accepted state
        result1 = await poller.poll(message1_id)
        result2 = await poller.poll(message2_id)

        assert result1
        assert result1.is_accepted
        assert result1.status == "accepted"
        assert not result1.is_success
        assert not result1.is_failure

        assert result2
        assert result2.is_accepted
        assert result2.status == "accepted"
        assert not result2.is_success
        assert not result2.is_failure

        # Now publish completion events to transition to completed state
        await app.publish(Message1CompletedSuccessfully(), headers={"correlation_id": message1_id})
        await app.publish(Message2CompletedSuccessfully(), headers={"correlation_id": message2_id})
        await anyio.sleep(0.5)

        # Poll again to verify they're now completed
        result1_completed = await poller.poll(message1_id)
        result2_completed = await poller.poll(message2_id)

        assert result1_completed
        assert result1_completed.is_success
        assert result1_completed.status == "completed"
        assert not result1_completed.is_accepted
        assert not result1_completed.is_failure

        assert result2_completed
        assert result2_completed.is_success
        assert result2_completed.status == "completed"
        assert not result2_completed.is_accepted
        assert not result2_completed.is_failure

        await app.stop()
