from __future__ import annotations

# Standard library imports
import json
from time import monotonic
from logging import Logger, getLogger
from typing import Awaitable, Callable, ClassVar, Dict, List, Optional

# Third-party imports
import aio_pika

# First-party imports
from models.configuration.rabbitmq_config import RabbitMqConfig
from models.enums import EventRoutingKey
from models.messaging.event_envelope import EventEnvelope
from service.observability.metrics import ApplicationMetrics
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

    #: How many times a quorum queue redelivers a message before dead-lettering
    #: it itself. This is protection against a message that poisons the
    #: *process* rather than the handler: a handler that raises already
    #: dead-letters, but one that is killed — an out-of-memory solve, say —
    #: never returns to reject anything, and without a limit the broker
    #: redelivers it for ever, taking a worker down on each attempt.
    DELIVERY_LIMIT: ClassVar[int] = 5

    def __init__(
        self,
        config: RabbitMqConfig,
        metrics: Optional[ApplicationMetrics] = None,
        role: str = "worker",
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the consumer.

        Args:
            config (RabbitMqConfig): The broker settings.
            metrics (Optional[ApplicationMetrics]): Where message figures are
                recorded. ``None`` records nothing.
            role (str): What to label this consumer's figures with.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            The role is a label rather than behaviour: this class does not care
            which queue it is consuming, but a dashboard very much does. Without
            it the planning worker's throughput and the notification worker's
            are one series, and the whole reason the two were split is that
            they are not comparable.
        """
        self.config = config
        self.metrics = metrics
        self.role = role
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

    def _record(self, routing_key: str, outcome: str, seconds: float) -> None:
        """Record how one message went, when anything is listening.

        Args:
            routing_key (str): The topic it arrived on.
            outcome (str): ``handled``, ``failed``, ``unhandled`` or
                ``unreadable``.
            seconds (float): How long the attempt took.

        Notes:
            Four outcomes rather than two, because they need different answers.
            ``failed`` is a handler that raised and a message that
            dead-lettered; ``unreadable`` is a message this version cannot
            parse, which usually means a deployment in progress; ``unhandled``
            is a topic bound to a queue nothing answers, which is a topology
            mistake and is silent without this.

            Guarded, because a consumer given no metrics records nothing rather
            than failing. Losing a figure must not lose a message.
        """
        if self.metrics is None:
            return
        self.metrics.record_message(self.role, routing_key, outcome, seconds)

    async def _dispatch(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:  # noqa: E501
        """Route one message to its handler.

        Args:
            message (aio_pika.abc.AbstractIncomingMessage): The message.

        Notes:
            ``requeue=False`` on failure. The message is dead-lettered, which
            keeps it for inspection without letting it block the queue behind
            it.
        """
        started = monotonic()
        async with message.process(requeue=False):
            try:
                envelope = EventEnvelope(**json.loads(message.body.decode("utf-8")))
            except Exception as exc:  # noqa: BLE001 - dead-lettered
                self.logger.error(
                    "Dropping an unreadable message on %s: %s.",
                    message.routing_key,
                    exc,
                )
                self._record(
                    str(message.routing_key), "unreadable", monotonic() - started
                )
                raise
            handler = self.handlers.get(envelope.routing_key)
            if handler is None:
                self.logger.warning(
                    "No handler for %s; the message is discarded.",
                    envelope.routing_key,
                )
                self._record(
                    envelope.routing_key, "unhandled", monotonic() - started
                )
                return
            self.logger.info("Handling %s.", envelope.routing_key)
            try:
                await handler(envelope)
            except Exception:
                # Counted before it is re-raised, because re-raising is what
                # dead-letters the message — and the rate of that is the single
                # figure worth alerting on here.
                self._record(envelope.routing_key, "failed", monotonic() - started)
                raise
            self._record(envelope.routing_key, "handled", monotonic() - started)
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

    async def _declare_dead_letter_queue(
        self, queue_name: str, routing_keys: List[EventRoutingKey]
    ) -> None:
        """Declare the one dead-letter queue this role's failures land on.

        Args:
            queue_name (str): The working queue's base name, without an agency.
            routing_keys (List[EventRoutingKey]): The topics this role handles.

        Notes:
            **One per role rather than one per agency.** The per-agency
            arrangement it replaces read well and did not scale: at a few
            hundred agencies it was a few hundred extra queues holding failures
            that arrive at a rate of nearly none.

            Bound to each of this role's topics across every agency, rather than
            to ``#``. The dead-letter exchange is shared, so ``#`` would collect
            the other role's failures too and a reader could not tell which
            worker had given up on what. The agency is still the last field of
            every key, so one agency's failures remain one selector away.

            Classic and durable rather than quorum. It holds a handful of
            messages that are read by a person, so replication buys little; and
            the whole point of consolidating it was to stop paying for a Raft
            cluster per agency.
        """
        if self.channel is None:
            raise MTConsumerNotStarted("start() must be called before consuming.")
        dead_name = f"{queue_name}{self.DEAD_LETTER_SUFFIX}"
        dead_queue = await self.channel.declare_queue(dead_name, durable=True)
        for routing_key in routing_keys:
            binding = f"{routing_key.value}.*"
            await dead_queue.bind(self.dead_letter, routing_key=binding)
            self.logger.debug(
                "Dead-letter queue %s is bound to %s.", dead_name, binding
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
            - **Quorum, not classic.** RabbitMQ 4 removed mirrored queues, so a
              durable classic queue on a cluster lives on exactly one node and
              goes with it — taking every planning run nobody had picked up yet.
              A quorum queue is replicated by Raft.

              **This cannot be changed on an existing queue.** Redeclaring one
              with a different ``x-queue-type`` is a ``PRECONDITION_FAILED``,
              not an upgrade, so an existing deployment needs the queues drained
              and deleted once — which is why it is done now rather than later,
              while there is at most one deployment to drain.
            - ``x-delivery-limit`` is what a quorum queue gives instead of the
              publisher's own care: a message redelivered that many times is
              dead-lettered by the broker. Without it a message that poisons the
              *process* — one that is killed rather than raising — is redelivered
              for ever, and each attempt takes a worker down with it.
            - **One dead-letter queue per role, not per agency.** It was
              per-agency, which reads well and does not scale: at a few hundred
              agencies that is a few hundred extra queues, each a Raft cluster
              of its own, holding failures that arrive at a rate of nearly none.
              The agency is still the last field of the routing key, so reading
              one agency's failures is still one selector.
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
            arguments={
                "x-queue-type": "quorum",
                "x-delivery-limit": self.DELIVERY_LIMIT,
                "x-dead-letter-exchange": self.dead_letter.name,
            },
        )
        for routing_key in routing_keys:
            binding = routing_key.scoped_to(company_id)
            await queue.bind(self.exchange, routing_key=binding)
            self.logger.info("Queue %s is bound to %s.", scoped_name, binding)
        await self._declare_dead_letter_queue(queue_name, routing_keys)
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
