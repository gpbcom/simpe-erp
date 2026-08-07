from __future__ import annotations

# Standard library imports
import asyncio
from datetime import UTC, datetime
import json
from logging import Logger, getLogger
from typing import Dict, Optional

# Third-party imports
import aio_pika
from pydantic import JsonValue

# First-party imports
from models.configuration.rabbitmq_config import RabbitMqConfig
from models.enums import EventRoutingKey
from models.messaging.event_envelope import EventEnvelope
from service.observability.trace_context import TraceContext


class EventPublisher:
    """Publishes the agency's events onto the broker.

    Attributes:
        config (RabbitMqConfig): Where the broker is and how to reach it.
        connection (Optional[AbstractRobustConnection]): The live connection,
            opened on first publish.
        exchange (Optional[AbstractExchange]): The declared topic exchange.
        lock (asyncio.Lock): Serialises the first connection attempt.
        logger (Logger): Logger for publishing.

    Notes:
        - **A failed publish never fails the request that caused it.**
          :meth:`publish` returns ``False`` and logs at ``ERROR``. A quote is
          submitted whether or not the broker was reachable; refusing the
          submission because a notification could not be queued would turn an
          outage of a convenience into an outage of the product. What is lost is
          the push, not the fact — the quote is in the database in
          ``pending-validation``, where the manager's queue reads it from.
        - The connection is opened once and reused. ``aio_pika``'s robust
          connection reconnects on its own, so a broker restart costs a
          reconnection rather than a process restart.
        - Messages are persistent and the exchange is durable. An event that
          survives being published must survive the broker being restarted, or
          the durability of the queue behind it buys nothing.
    """

    def __init__(self, config: RabbitMqConfig, logger: Optional[Logger] = None) -> None:
        """Initialize the publisher.

        Args:
            config (RabbitMqConfig): The broker settings.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self.exchange: Optional[aio_pika.abc.AbstractExchange] = None
        self.lock = asyncio.Lock()
        self.traces = TraceContext(logger=self.logger)
        self.logger.debug("EventPublisher created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _exchange_or_none(self) -> Optional[aio_pika.abc.AbstractExchange]:  # noqa: E501
        """Return the exchange, connecting on first use.

        Returns:
            Optional[aio_pika.abc.AbstractExchange]: The declared exchange, or
            ``None`` when the broker cannot be reached.

        Notes:
            Guarded by a lock so that a burst of concurrent publishes on a cold
            process opens one connection rather than one each.
        """
        if self.exchange is not None:
            return self.exchange
        async with self.lock:
            if self.exchange is not None:
                return self.exchange
            try:
                self.connection = await aio_pika.connect_robust(
                    self.config.build_url(),
                    timeout=self.config.publish_timeout_seconds,
                )
                channel = await self.connection.channel(publisher_confirms=True)  # noqa: E501
                self.exchange = await channel.declare_exchange(
                    self.config.exchange,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                self.logger.info(
                    "Connected to the broker at %s, exchange %s.",
                    self.config.url_without_password(),
                    self.config.exchange,
                )
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                self.logger.error(
                    "Could not reach the broker at %s: %s.",
                    self.config.url_without_password(),
                    exc,
                )
                self.connection = None
                self.exchange = None
        return self.exchange

    ############################
    # Publicly Exposed Methods #
    ############################

    async def publish(
        self,
        routing_key: EventRoutingKey,
        company_id: str,
        payload: Optional[Dict[str, JsonValue]] = None,
    ) -> bool:
        """Publish one event, addressed to one agency.

        Args:
            routing_key (EventRoutingKey): The topic to publish under.
            company_id (str): The agency the event belongs to.
            payload (Optional[Dict[str, JsonValue]]): The event's fields.

        Returns:
            bool: ``True`` when the broker confirmed the message, ``False``
            when it was disabled or unreachable.

        Raises:
            ValueError: If ``company_id`` is empty.

        Notes:
            - **``company_id`` is required and has no default.** It decides
              which agency's queue the message lands in, so a default would
              mean a forgotten argument still publishes — to the wrong agency,
              or to a key nothing is bound to. A missing one is a ``TypeError``
              at the call site instead, which is the failure you want.
            - The identifier is not put in the payload in place of the routing
              key. A payload field is read after delivery, and by then the
              message has already been handed to whichever queue the key chose.
              Isolation has to be in the key.
            - The return value exists so a caller *may* react — the seeder logs
              a warning, a test asserts on it — but no caller in the
              application treats ``False`` as an error. That is deliberate: see
              the class note.
        """
        scoped = routing_key.scoped_to(company_id)
        if not self.config.enabled:
            self.logger.debug("Broker disabled; dropping %s.", scoped)
            return False
        exchange = await self._exchange_or_none()
        if exchange is None:
            self.logger.error(
                "Dropped %s: the broker is unreachable. The database still "
                "holds the fact; only the push was lost.",
                scoped,
            )
            return False
        envelope = EventEnvelope(
            routing_key=routing_key.value,
            payload=payload or {},
            occurred_at=datetime.now(UTC),
            # Carried so the solve this queues traces back to the request that
            # asked for it. ``None`` when nothing is being traced, which is what
            # makes the field nullable rather than merely optional.
            traceparent=self.traces.current(),
        )
        body = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        try:
            await exchange.publish(
                aio_pika.Message(
                    body=body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=scoped,
            )
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            self.logger.error("Could not publish %s: %s.", scoped, exc)
            # Forget the channel so the next publish reconnects rather than
            # failing again against a socket that has already gone.
            self.exchange = None
            return False
        self.logger.info("Published %s.", scoped)
        return True

    async def close(self) -> None:
        """Close the broker connection.

        Notes:
            Called from the application's shutdown hook. Closing is best-effort:
            a process on its way out must not hang on a broker that has already
            gone.
        """
        if self.connection is None:
            return
        try:
            await self.connection.close()
            self.logger.info("Closed the broker connection.")
        except Exception as exc:  # noqa: BLE001 - shutting down regardless
            self.logger.warning("Could not close the broker connection: %s.", exc)
        finally:
            self.connection = None
            self.exchange = None
