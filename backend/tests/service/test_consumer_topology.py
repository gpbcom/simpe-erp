from __future__ import annotations

# Standard library imports
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.rabbitmq_config import RabbitMqConfig
from models.enums import EventRoutingKey
from service.messaging.consumer import EventConsumer
from service.messaging.exceptions import MTConsumerNotStarted
from tests.annotations import ModelInput

PLANNING_KEYS: List[EventRoutingKey] = [EventRoutingKey.PLANNING_RUN_REQUESTED]
NOTIFICATION_KEYS: List[EventRoutingKey] = [
    EventRoutingKey.QUOTE_SUBMITTED,
    EventRoutingKey.QUOTE_VALIDATED,
]


@pytest.fixture
def consumer() -> EventConsumer:
    """Return a consumer wired to stand-in broker objects.

    Returns:
        EventConsumer: A consumer that believes it has started, over mocks that
        record what was declared and bound.

    Notes:
        The channel is a mock rather than a broker. What is under test is the
        *topology* — the arguments a queue is declared with and the keys it is
        bound to — which is decided entirely in this class and is exactly what
        an integration test against a live broker would not tell apart from a
        working one.
    """
    consumer = EventConsumer(config=RabbitMqConfig())
    consumer.channel = AsyncMock()
    consumer.exchange = MagicMock(name="simple-erp")
    consumer.dead_letter = MagicMock()
    consumer.dead_letter.name = "simple-erp.dlx"
    consumer.channel.declare_queue = AsyncMock(side_effect=lambda *a, **k: AsyncMock())
    return consumer


def _declared(consumer: EventConsumer, name: str) -> Dict[str, ModelInput]:
    """Return the keyword arguments one queue was declared with.

    Args:
        consumer (EventConsumer): The consumer under test.
        name (str): The queue's full name.

    Returns:
        Dict[str, ModelInput]: The declaration's keyword arguments.
    """
    for call in consumer.channel.declare_queue.await_args_list:
        if call.args and call.args[0] == name:
            return call.kwargs
    raise AssertionError(f"{name} was never declared.")


class TestWorkingQueueTopology:
    """Tests for how an agency's own queue is declared."""

    async def test_the_queue_is_replicated(self, consumer: EventConsumer) -> None:
        """**RabbitMQ 4 removed mirrored queues.**

        Notes:
            A durable *classic* queue on a cluster lives on exactly one node and
            goes with it — taking every planning run nobody had picked up yet.
            Durability is not replication, and the two look identical in a
            single-node development stack.
        """
        await consumer.consume_for_company("planning-runs", PLANNING_KEYS, "company-1")

        arguments = _declared(consumer, "planning-runs.company-1")["arguments"]
        assert arguments["x-queue-type"] == "quorum"

    async def test_a_message_is_not_redelivered_for_ever(
        self, consumer: EventConsumer
    ) -> None:
        """A limit is what protects against a message that poisons the process.

        Notes:
            A handler that *raises* already dead-letters. One that is **killed**
            — an out-of-memory solve — never returns to reject anything, so
            without this the broker redelivers it indefinitely and each attempt
            takes a worker down with it.
        """
        await consumer.consume_for_company("planning-runs", PLANNING_KEYS, "company-1")

        arguments = _declared(consumer, "planning-runs.company-1")["arguments"]
        assert arguments["x-delivery-limit"] == EventConsumer.DELIVERY_LIMIT
        assert arguments["x-delivery-limit"] > 0

    async def test_failures_leave_by_the_dead_letter_exchange(
        self, consumer: EventConsumer
    ) -> None:
        """A rejected message is kept rather than dropped."""
        await consumer.consume_for_company("planning-runs", PLANNING_KEYS, "company-1")

        arguments = _declared(consumer, "planning-runs.company-1")["arguments"]
        assert arguments["x-dead-letter-exchange"] == "simple-erp.dlx"

    async def test_the_queue_is_the_agency_s_own(self, consumer: EventConsumer) -> None:
        """One agency's backlog must not delay another's."""
        await consumer.consume_for_company("planning-runs", PLANNING_KEYS, "company-7")

        _declared(consumer, "planning-runs.company-7")

    async def test_consuming_before_starting_is_refused(self) -> None:
        """A queue declared on no channel would fail far from the cause."""
        consumer = EventConsumer(config=RabbitMqConfig())

        with pytest.raises(MTConsumerNotStarted):
            await consumer.consume_for_company(
                "planning-runs", PLANNING_KEYS, "company-1"
            )


class TestDeadLetterQueueTopology:
    """Tests for where a role's failures collect."""

    async def test_there_is_one_per_role_not_one_per_agency(
        self, consumer: EventConsumer
    ) -> None:
        """**The per-agency arrangement read well and did not scale.**

        Notes:
            At a few hundred agencies it was a few hundred extra queues, each a
            Raft cluster of its own, holding failures that arrive at a rate of
            nearly none. Two agencies here declare one dead-letter queue between
            them.
        """
        await consumer.consume_for_company("planning-runs", PLANNING_KEYS, "company-1")
        await consumer.consume_for_company("planning-runs", PLANNING_KEYS, "company-2")

        declared = [
            call.args[0]
            for call in consumer.channel.declare_queue.await_args_list
            if call.args
        ]
        assert declared.count("planning-runs.dlx") == 2  # idempotent redeclaration
        assert "planning-runs.dlx.company-1" not in declared
        assert "planning-runs.dlx.company-2" not in declared

    async def test_every_topic_the_role_handles_is_bound_and_no_others(
        self, consumer: EventConsumer
    ) -> None:
        """**Each of this role's topics, and not ``#``.**

        Notes:
            A failure on an *unbound* topic is dead-lettered into nothing: the
            exchange accepts it, no queue matches, and the message is discarded
            — the one outcome dead-lettering exists to prevent.

            A catch-all binding has the opposite fault. The dead-letter exchange
            is shared between the roles, so ``#`` would put planning failures
            and notification failures in one queue and leave a reader unable to
            tell which worker had given up on what.
        """
        queues: Dict[str, AsyncMock] = {}

        def declare(name: str, **_: ModelInput) -> AsyncMock:
            queues[name] = queues.get(name, AsyncMock())
            return queues[name]

        consumer.channel.declare_queue = AsyncMock(side_effect=declare)

        await consumer.consume_for_company(
            "quote-notifications", NOTIFICATION_KEYS, "company-1"
        )

        bound = {
            call.kwargs["routing_key"]
            for call in queues["quote-notifications.dlx"].bind.await_args_list
        }
        assert bound == {"quote.submitted.*", "quote.validated.*"}

    async def test_an_agency_is_still_one_selector_away(
        self, consumer: EventConsumer
    ) -> None:
        """Consolidating the queue must not cost per-agency reading.

        Notes:
            The agency is the last field of every routing key, and a
            dead-lettered message keeps the key it arrived on — so one agency's
            failures are still selectable, just not in a queue of their own.
        """
        queues: Dict[str, AsyncMock] = {}

        def declare(name: str, **_: ModelInput) -> AsyncMock:
            queues[name] = queues.get(name, AsyncMock())
            return queues[name]

        consumer.channel.declare_queue = AsyncMock(side_effect=declare)

        await consumer.consume_for_company("planning-runs", PLANNING_KEYS, "company-1")

        bound = {
            call.kwargs["routing_key"]
            for call in queues["planning-runs.dlx"].bind.await_args_list
        }
        assert all(binding.endswith(".*") for binding in bound)
