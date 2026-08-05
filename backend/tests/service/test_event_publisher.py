from __future__ import annotations

# Standard library imports
import json
from typing import List
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.rabbitmq_config import RabbitMqConfig
from models.enums import EventRoutingKey
from models.messaging.event_envelope import EventEnvelope
from service.messaging.publisher import EventPublisher


@pytest.fixture
def published() -> List[EventEnvelope]:
    """Collect the envelopes a publisher hands to the broker.

    Returns:
        List[EventEnvelope]: The captured envelopes, filled by the fixture
        below as messages are published.
    """
    return []


@pytest.fixture
def publisher(
    monkeypatch: pytest.MonkeyPatch, published: List[EventEnvelope]
) -> EventPublisher:
    """Return a publisher whose exchange records rather than sends.

    Args:
        monkeypatch (pytest.MonkeyPatch): Used to replace the connection step.
        published (List[EventEnvelope]): Where captured envelopes are put.

    Returns:
        EventPublisher: An enabled publisher over a stand-in exchange.

    Notes:
        The connection itself is replaced rather than a broker being started.
        What is worth testing here is the envelope, the routing key and the
        never-raise contract; that a real AMQP socket works is aio-pika's test
        suite, not this one. The integration test against a live broker is
        marked separately.
    """
    exchange = AsyncMock()

    async def _capture(message, routing_key: str) -> None:
        """Record a published message instead of sending it.

        Args:
            message: The aio-pika message.
            routing_key (str): The topic it was published under.
        """
        published.append(EventEnvelope(**json.loads(message.body.decode("utf-8"))))

    exchange.publish = AsyncMock(side_effect=_capture)
    service = EventPublisher(config=RabbitMqConfig(enabled=True))
    monkeypatch.setattr(service, "_exchange_or_none", AsyncMock(return_value=exchange))
    return service


class TestEventPublisher:
    """Tests for publishing an event onto the broker."""

    async def test_a_published_event_carries_its_routing_key_and_payload(
        self, publisher: EventPublisher, published: List[EventEnvelope]
    ) -> None:
        """The envelope is what the consumer will read back."""
        sent = await publisher.publish(
            EventRoutingKey.QUOTE_SUBMITTED, {"quote_id": "quote-1"}
        )

        assert sent is True
        assert published[0].routing_key == "quote.submitted"
        assert published[0].string_field("quote_id") == "quote-1"
        assert published[0].occurred_at is not None

    async def test_a_disabled_broker_drops_the_event_without_failing(
        self, published: List[EventEnvelope]
    ) -> None:
        """A developer with no broker must still be able to use the app.

        Notes:
            Disabled is the default, so this is the path most local runs take.
        """
        service = EventPublisher(config=RabbitMqConfig(enabled=False))

        sent = await service.publish(EventRoutingKey.QUOTE_SUBMITTED, {})

        assert sent is False
        assert published == []

    async def test_an_unreachable_broker_never_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The request that caused the event must still succeed.

        Notes:
            **This is the contract the whole design rests on.** A quote is
            submitted whether or not the broker was reachable; refusing the
            submission because a notification could not be queued would turn an
            outage of a convenience into an outage of the product.
        """
        service = EventPublisher(config=RabbitMqConfig(enabled=True))
        monkeypatch.setattr(service, "_exchange_or_none", AsyncMock(return_value=None))

        sent = await service.publish(EventRoutingKey.PLANNING_RUN_REQUESTED, {})

        assert sent is False

    async def test_a_failing_publish_never_raises(
        self, publisher: EventPublisher
    ) -> None:
        """A broker that accepts the connection but drops the write."""
        exchange = AsyncMock()
        exchange.publish = AsyncMock(side_effect=OSError("connection reset"))
        publisher._exchange_or_none = AsyncMock(return_value=exchange)

        sent = await publisher.publish(EventRoutingKey.QUOTE_VALIDATED, {})

        assert sent is False

    async def test_a_failed_publish_forgets_the_channel(
        self, publisher: EventPublisher
    ) -> None:
        """The next publish reconnects rather than reusing a dead socket."""
        exchange = AsyncMock()
        exchange.publish = AsyncMock(side_effect=OSError("connection reset"))
        publisher._exchange_or_none = AsyncMock(return_value=exchange)
        publisher.exchange = exchange

        await publisher.publish(EventRoutingKey.QUOTE_REFUSED, {})

        assert publisher.exchange is None


class TestEventEnvelope:
    """Tests for the message shape every consumer reads."""

    def test_a_missing_field_reads_as_none(self) -> None:
        """A consumer must survive a message an older publisher wrote."""
        envelope = EventEnvelope(routing_key="quote.submitted", payload={})

        assert envelope.string_field("quote_id") is None

    def test_a_non_string_field_reads_as_none(self) -> None:
        """A malformed field is indistinguishable from a missing one.

        Notes:
            Which is what the handler wants either way — there is nothing
            useful it could do with an integer where an identifier belongs.
        """
        envelope = EventEnvelope(
            routing_key="quote.submitted", payload={"quote_id": 42}
        )

        assert envelope.string_field("quote_id") is None
