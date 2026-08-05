from __future__ import annotations

# Standard library imports
import json
from logging import Logger, getLogger
from typing import Awaitable, Callable, ClassVar, Dict, List, Optional

# Third-party imports
import aio_pika

# First-party imports
from models.configuration.rabbitmq_config import RabbitMqConfig
from models.enums import EventRoutingKey
from models.messaging.event_envelope import EventEnvelope

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventConsumer:
    """Runs a queue's handler for every message that arrives on it.

    Attributes:
        DEAD_LETTER_SUFFIX (ClassVar[str]): Appended to the exchange name to
            form the dead-letter exchange.
        config (RabbitMqConfig): Where the broker is and how to reach it.
        handlers (Dict[str, EventHandler]): The handler for each routing key.
        logger (Logger): Logger for consumption.

    Notes:
        - **A message is acknowledged only once its handler returns.** A worker
          killed mid-solve leaves the message unacknowledged, and the broker
          redelivers it to the next worker. The alternative — acknowledging on
          receipt — loses the planning run entirely, which is the failure the
          move off ``BackgroundTasks`` was meant to end.
        - A handler that raises rejects the message without requeuing it, so it
          goes to the dead-letter exchange rather than round the loop for ever.
          A message that fails once will usually fail again, and a poison
          message spinning at full speed is how a broker outage becomes a
          database outage.
        - The consumer declares the same durable topic exchange the publisher
          does. Declaring is idempotent, and it means neither side has to be
          started first.
    """

    DEAD_LETTER_SUFFIX: ClassVar[str] = ".dlx"

    def __init__(
        self,
        config: RabbitMqConfig,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the consumer.

        Args:
            config (RabbitMqConfig): The broker settings.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.config = config
        self.handlers: Dict[str, EventHandler] = {}
        self.logger = logger if logger else getLogger(__name__)
        self.connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
        self.logger.debug("EventConsumer created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _dispatch(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        """Route one message to its handler.

        Args:
            message (aio_pika.abc.AbstractIncomingMessage): The message.

        Notes:
            ``requeue=False`` on failure. The message is dead-lettered, which
            keeps it for inspection without letting it block the queue behind
            it.
        """
        async with message.process(requeue=False):
            try:
                envelope = EventEnvelope(**json.loads(message.body.decode("utf-8")))
            except Exception as exc:  # noqa: BLE001 - dead-lettered
                self.logger.error(
                    "Dropping an unreadable message on %s: %s.",
                    message.routing_key,
                    exc,
                )
                raise
            handler = self.handlers.get(envelope.routing_key)
            if handler is None:
                self.logger.warning(
                    "No handler for %s; the message is discarded.",
                    envelope.routing_key,
                )
                return
            self.logger.info("Handling %s.", envelope.routing_key)
            await handler(envelope)
            self.logger.debug("Handled %s.", envelope.routing_key)

    ############################
    # Publicly Exposed Methods #
    ############################

    def on(self, routing_key: EventRoutingKey, handler: EventHandler) -> None:
        """Register the handler for a routing key.

        Args:
            routing_key (EventRoutingKey): The topic to handle.
            handler (EventHandler): The coroutine to run for it.
        """
        self.handlers[routing_key.value] = handler
        self.logger.debug("Registered a handler for %s.", routing_key.value)

    async def run(self, queue_name: str, routing_keys: List[EventRoutingKey]) -> None:  # noqa: E501
        """Consume a queue until the process is stopped.

        Args:
            queue_name (str): The durable queue to consume.
            routing_keys (List[EventRoutingKey]): The topics to bind it to.

        Raises:
            Exception: Whatever the broker raises when it cannot be reached.
                A worker with no broker has nothing to do, so unlike the
                publisher it fails loudly and lets the supervisor restart it.
        """
        self.connection = await aio_pika.connect_robust(self.config.build_url())  # noqa: E501
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=self.config.prefetch)
        exchange = await channel.declare_exchange(
            self.config.exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        dead_letter = await channel.declare_exchange(
            f"{self.config.exchange}{self.DEAD_LETTER_SUFFIX}",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            arguments={"x-dead-letter-exchange": dead_letter.name},
        )
        for routing_key in routing_keys:
            await queue.bind(exchange, routing_key=routing_key.value)
            self.logger.info("Queue %s is bound to %s.", queue_name, routing_key.value)
        dead_queue = await channel.declare_queue(
            f"{queue_name}{self.DEAD_LETTER_SUFFIX}", durable=True
        )
        await dead_queue.bind(dead_letter, routing_key="#")
        self.logger.info(
            "Consuming %s with prefetch %d.", queue_name, self.config.prefetch
        )
        await queue.consume(self._dispatch)

    async def close(self) -> None:
        """Close the broker connection.

        Notes:
            Best-effort, like the publisher's: a worker shutting down must not
            hang waiting on a broker that has already gone.
        """
        if self.connection is None:
            return
        try:
            await self.connection.close()
            self.logger.info("Closed the consumer connection.")
        except Exception as exc:  # noqa: BLE001 - shutting down regardless
            self.logger.warning("Could not close the consumer connection: %s.", exc)
        finally:
            self.connection = None
