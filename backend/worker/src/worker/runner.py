from __future__ import annotations

# Standard library imports
import asyncio
from logging import Logger, getLogger
import signal
from typing import ClassVar, List, Optional

# First-party imports
from models.configuration.app_config import AppConfig
from models.enums import EventRoutingKey
from service.messaging.consumer import EventConsumer
from worker.handlers import EventHandlers


class WorkerRunner:
    """Consumes every agency's queues until the process is asked to stop.

    Attributes:
        PLANNING_QUEUE (ClassVar[str]): Base name of the planning queue.
        NOTIFICATION_QUEUE (ClassVar[str]): Base name of the notification
            queue.
        NOTIFICATION_KEYS (ClassVar[tuple]): The topics the notification queue
            binds.
        config (AppConfig): The whole application configuration.
        handlers (EventHandlers): What runs when a message arrives.
        planning (EventConsumer): Consumer for the planning queues.
        notifications (EventConsumer): Consumer for the notification queues.
        lifecycle (EventConsumer): Consumer for ``company.created``.
        logger (Logger): Logger for the worker's lifecycle.

    Notes:
        - **A queue per agency per kind of work.** The planning solve pins a
          core for thirty seconds; sharing a queue with the notification
          fan-out would leave a manager waiting half a minute to be told a
          quote needs looking at. Splitting again by agency means one agency's
          backlog or poison message is its own, rather than something every
          other agency waits behind.
        - The agencies are enumerated once at startup and then kept current by
          the ``company.created`` announcement, so an agency founded through
          self-registration is served without a restart. The enumeration is
          what makes the announcement queue safe to be non-durable: anything
          missed while this process was down is picked up next time it starts.
        - A class rather than one long function because :meth:`serve` has to be
          callable from two places — the startup sweep and the announcement
          handler — and a closure over the consumers would be a nested function
          holding the process's whole state.
    """

    PLANNING_QUEUE: ClassVar[str] = "planning-runs"
    NOTIFICATION_QUEUE: ClassVar[str] = "quote-notifications"
    NOTIFICATION_KEYS: ClassVar[tuple] = (
        EventRoutingKey.QUOTE_SUBMITTED,
        EventRoutingKey.QUOTE_VALIDATED,
        EventRoutingKey.QUOTE_REFUSED,
        EventRoutingKey.PLANNING_RUN_COMPLETED,
    )

    def __init__(self, config: AppConfig, logger: Optional[Logger] = None) -> None:
        """Initialize the runner.

        Args:
            config (AppConfig): The application configuration.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.handlers = EventHandlers(config=config, logger=self.logger)
        self.planning = EventConsumer(config=config.rabbitmq, logger=self.logger)
        self.notifications = EventConsumer(config=config.rabbitmq, logger=self.logger)
        self.lifecycle = EventConsumer(config=config.rabbitmq, logger=self.logger)
        self.logger.debug("WorkerRunner created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _register_handlers(self) -> None:
        """Wire each topic to the coroutine that answers it."""
        self.planning.on(
            EventRoutingKey.PLANNING_RUN_REQUESTED, self.handlers.run_planning
        )
        self.notifications.on(
            EventRoutingKey.QUOTE_SUBMITTED, self.handlers.quote_submitted
        )
        self.notifications.on(
            EventRoutingKey.QUOTE_VALIDATED, self.handlers.quote_validated
        )
        self.notifications.on(
            EventRoutingKey.QUOTE_REFUSED, self.handlers.quote_refused
        )
        self.notifications.on(
            EventRoutingKey.PLANNING_RUN_COMPLETED, self.handlers.planning_completed
        )
        self.lifecycle.on(
            EventRoutingKey.COMPANY_CREATED, self.handlers.company_created
        )

    async def _wait_for_a_signal(self) -> None:
        """Block until the process is asked to stop.

        Notes:
            The signals are handled rather than left to the default, so an
            in-flight solve is allowed to finish and acknowledge instead of
            being killed mid-message and redelivered from the start.
        """
        stopping = asyncio.Event()
        loop = asyncio.get_running_loop()
        for received in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(received, stopping.set)
        await stopping.wait()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def serve(self, company_id: str) -> None:
        """Bind and consume one agency's queues.

        Args:
            company_id (str): The agency to serve.

        Notes:
            Idempotent, because declaring a queue that already exists is. That
            matters: a restart racing a ``company.created`` announcement can
            reach the same agency twice, and the safe ordering below relies on
            being able to.
        """
        await self.planning.consume_for_company(
            self.PLANNING_QUEUE,
            [EventRoutingKey.PLANNING_RUN_REQUESTED],
            company_id,
        )
        await self.notifications.consume_for_company(
            self.NOTIFICATION_QUEUE,
            list(self.NOTIFICATION_KEYS),
            company_id,
        )

    async def start(self) -> List[str]:
        """Connect, bind every agency, and begin consuming.

        Returns:
            List[str]: The agencies now being served.

        Notes:
            The announcement queue is bound **before** the agencies are
            enumerated, not after. An agency founded between the enumeration
            and the binding would otherwise fall through the gap: too late to
            be listed, too early to be announced. Overlapping the two is safe
            because :meth:`serve` is idempotent; leaving a gap is not.
        """
        # Before any consumer is started, so no message can be delivered to a
        # handler that has no database behind it.
        await self.handlers.open()
        self._register_handlers()
        await self.planning.start()
        await self.notifications.start()
        await self.lifecycle.start()

        self.handlers.on_company_created(self.serve)
        await self.lifecycle.consume_every_company([EventRoutingKey.COMPANY_CREATED])
        served = await self.handlers.companies()
        for company_id in served:
            await self.serve(company_id)
        self.logger.info("Worker is consuming; waiting for messages.")
        return served

    async def run(self) -> None:
        """Start, then consume until the process is asked to stop."""
        await self.start()
        await self._wait_for_a_signal()
        self.logger.info("Worker is shutting down.")
        await self.close()

    async def close(self) -> None:
        """Release every broker connection and the database pool."""
        await self.lifecycle.close()
        await self.planning.close()
        await self.notifications.close()
        await self.handlers.close()
