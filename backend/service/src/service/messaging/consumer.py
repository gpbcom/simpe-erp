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
from service.messaging.exceptions import MTConsumerNotStarted

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
        self.channel: Optional[aio_pika.abc.AbstractChannel] = None
        self.exchange: Optional[aio_pika.abc.AbstractExchange] = None
        self.dead_letter: Optional[aio_pika.abc.AbstractExchange] = None
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

    async def start(self) -> None:
        """Open the connection and declare the exchanges.

        Raises:
            Exception: Whatever the broker raises when it cannot be reached.
                A worker with no broker has nothing to do, so unlike the
                publisher it fails loudly and lets the supervisor restart it.

        Notes:
            Separated from binding a queue because an agency can be founded
            while this process is running. The connection, the channel and the
            exchanges are per-process; the queues are per-agency and arrive one
            at a time.
        """
        self.connection = await aio_pika.connect_robust(self.config.build_url())  # noqa: E501
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=self.config.prefetch)
        self.exchange = await self.channel.declare_exchange(
            self.config.exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self.dead_letter = await self.channel.declare_exchange(
            f"{self.config.exchange}{self.DEAD_LETTER_SUFFIX}",
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        self.logger.info(
            "Connected to %s; exchange %s is ready.",
            self.config.url_without_password(),
            self.config.exchange,
        )

    async def consume_for_company(
        self,
        queue_name: str,
        routing_keys: List[EventRoutingKey],
        company_id: str,
    ) -> None:
        """Consume one agency's queue.

        Args:
            queue_name (str): The queue's base name, without the agency.
            routing_keys (List[EventRoutingKey]): The topics to bind it to.
            company_id (str): The agency whose traffic this queue carries.

        Notes:
            - **A queue per agency, not a shared one.** A poison message or a
              backlog belongs to the agency that produced it: one agency
              submitting a thousand quotes, or one whose handler keeps failing,
              must not delay another agency's notifications behind it. A single
              queue makes every agency wait for the slowest.
            - The dead-letter queue is per-agency for the same reason, and so
              that reading one agency's failures does not mean reading
              everybody's.
            - Declaring is idempotent, so binding an agency twice — a restart
              racing a ``company.created`` — is harmless rather than an error
              to guard against.
        """
        if self.channel is None or self.exchange is None:
            raise MTConsumerNotStarted("start() must be called before consuming.")
        scoped_name = f"{queue_name}.{company_id}"
        queue = await self.channel.declare_queue(
            scoped_name,
            durable=True,
            arguments={"x-dead-letter-exchange": self.dead_letter.name},
        )
        for routing_key in routing_keys:
            binding = routing_key.scoped_to(company_id)
            await queue.bind(self.exchange, routing_key=binding)
            self.logger.info("Queue %s is bound to %s.", scoped_name, binding)
        dead_queue = await self.channel.declare_queue(
            f"{scoped_name}{self.DEAD_LETTER_SUFFIX}", durable=True
        )
        await dead_queue.bind(self.dead_letter, routing_key=f"#.{company_id}")
        await queue.consume(self._dispatch)
        self.logger.info(
            "Consuming %s with prefetch %d.", scoped_name, self.config.prefetch
        )

    async def consume_every_company(self, routing_keys: List[EventRoutingKey]) -> None:
        """Consume one topic across every agency, on a queue of this worker's own.

        Args:
            routing_keys (List[EventRoutingKey]): The topics to bind, each
                under the ``*`` wildcard.

        Notes:
            - For the control plane only: this is how a worker hears that an
              agency has been founded and binds its queues without a restart.
            - **Exclusive and server-named**, so every worker process gets its
              own copy. A durable shared queue would hand each announcement to
              exactly one worker, and the others would never learn the agency
              exists — they would run on, quietly serving every agency but that
              one.
            - Nothing durable is wanted here either: an announcement missed
              while a worker was down is recovered by the enumeration it does
              at startup.
        """
        if self.channel is None or self.exchange is None:
            raise MTConsumerNotStarted("start() must be called before consuming.")
        queue = await self.channel.declare_queue(exclusive=True)
        for routing_key in routing_keys:
            binding = f"{routing_key.value}.*"
            await queue.bind(self.exchange, routing_key=binding)
            self.logger.info("Exclusive queue is bound to %s.", binding)
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
