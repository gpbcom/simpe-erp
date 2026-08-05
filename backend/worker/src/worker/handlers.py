from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Optional

# First-party imports
from models.configuration.app_config import AppConfig
from models.enums import EventRoutingKey, NotificationKind
from models.messaging.event_envelope import EventEnvelope
from service.messaging.publisher import EventPublisher
from service.notifications.notifications import NotificationService
from service.planning.plannings import PlanningService
from storage.db.connection_manager import DatabaseConnectionManager
from storage.repositories.customer import CustomerRepository
from storage.repositories.hca import HcaRepository
from storage.repositories.intervention import InterventionRepository
from storage.repositories.notification import NotificationRepository
from storage.repositories.planning_run import PlanningRunRepository
from storage.repositories.planning_settings import PlanningSettingsRepository
from storage.repositories.quote import QuoteRepository
from storage.repositories.user import UserRepository


class EventHandlers:
    """What the worker actually does when a message arrives.

    Attributes:
        config (AppConfig): The whole application configuration.
        publisher (EventPublisher): Used to announce a finished planning run.
        logger (Logger): Logger for handled events.

    Notes:
        - **Each handler opens its own session and closes it before returning.**
          A worker holds a connection for as long as it holds one, and a solve
          runs for thirty seconds; keeping a session open across that would tie
          up a pooled connection per in-flight message for no reason. It also
          means a handler that fails rolls back cleanly and the redelivery
          starts from a known state.
        - The payloads carry identifiers, and every handler re-reads the record.
          A message may be minutes old by the time it is handled — the queue may
          have backed up, or the worker may have been restarted — and acting on
          a copy embedded in the message would act on the world as it was, not
          as it is.
        - A handler that cannot do its work **raises**, so the message is
          dead-lettered rather than silently dropped. The one exception is a
          record that no longer exists, which is logged and acknowledged: a
          quote deleted between submission and handling is not an error, and
          retrying it for ever would never succeed.
    """

    def __init__(self, config: AppConfig, logger: Optional[Logger] = None) -> None:
        """Initialize the handlers.

        Args:
            config (AppConfig): The application configuration.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.publisher = EventPublisher(config=config.rabbitmq, logger=self.logger)
        self._manager = DatabaseConnectionManager(
            config=config.database, logger=self.logger
        )
        self.logger.debug("EventHandlers created.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def run_planning(self, envelope: EventEnvelope) -> None:
        """Solve a planning run that the API asked for.

        Args:
            envelope (EventEnvelope): The message, carrying ``run_id``.

        Raises:
            Exception: Whatever the solve raises, so the message is
                dead-lettered and the failure is visible.

        Notes:
            This is the work that used to run in a FastAPI ``BackgroundTask``.
            Moving it here fixes two things at once: a restart no longer loses
            an in-flight run, because the message is only acknowledged when the
            solve has finished; and a thirty-second solve no longer occupies a
            web worker that should be answering requests.
        """
        run_id = envelope.string_field("run_id")
        if run_id is None:
            self.logger.error("A planning message named no run; discarding it.")
            return
        self.logger.info("Solving planning run %s.", run_id)
        async with self._manager.session() as session:
            service = PlanningService(
                runs=PlanningRunRepository(session=session, logger=self.logger),
                interventions=InterventionRepository(
                    session=session, logger=self.logger
                ),
                quotes=QuoteRepository(session=session, logger=self.logger),
                customers=CustomerRepository(session=session, logger=self.logger),
                hcas=HcaRepository(session=session, logger=self.logger),
                settings=PlanningSettingsRepository(
                    session=session, logger=self.logger
                ),
                config=self.config.planning,
                logger=self.logger,
            )
            run = await service.execute_run(run_id)
        self.logger.info("Planning run %s finished as %s.", run_id, run.status.value)
        await self.publisher.publish(
            EventRoutingKey.PLANNING_RUN_COMPLETED,
            {"run_id": run_id, "status": run.status.value},
        )

    async def quote_submitted(self, envelope: EventEnvelope) -> None:
        """Tell the agency's supervisors that a quote needs validating.

        Args:
            envelope (EventEnvelope): The message, carrying ``quote_id``,
                ``reference``, ``company_id`` and ``author_name``.
        """
        quote_id = envelope.string_field("quote_id")
        reference = envelope.string_field("reference") or "?"
        author = envelope.string_field("author_name") or "un intervenant"
        async with self._manager.session() as session:
            service = self._notifications(session)
            await service.notify_supervisors(
                company_id=envelope.string_field("company_id"),
                kind=NotificationKind.QUOTE_SUBMITTED,
                title=f"Devis {reference} à valider",
                body=f"{author} a soumis le devis {reference} pour validation.",
                quote_id=quote_id,
            )

    async def quote_validated(self, envelope: EventEnvelope) -> None:
        """Tell an assistant that the quote they wrote was approved.

        Args:
            envelope (EventEnvelope): The message, carrying ``quote_id``,
                ``reference`` and ``author_id``.
        """
        await self._notify_author(
            envelope,
            kind=NotificationKind.QUOTE_VALIDATED,
            title_template="Devis {reference} validé",
            body_template="Votre devis {reference} a été validé et envoyé au client.",
        )

    async def quote_refused(self, envelope: EventEnvelope) -> None:
        """Tell an assistant that the quote they wrote came back.

        Args:
            envelope (EventEnvelope): The message, carrying ``quote_id``,
                ``reference`` and ``author_id``.
        """
        await self._notify_author(
            envelope,
            kind=NotificationKind.QUOTE_REFUSED,
            title_template="Devis {reference} à corriger",
            body_template=(
                "Votre devis {reference} vous a été retourné. Vous pouvez le "
                "modifier et le soumettre à nouveau."
            ),
        )

    async def planning_completed(self, envelope: EventEnvelope) -> None:
        """Tell the supervisors that a planning run finished.

        Args:
            envelope (EventEnvelope): The message, carrying ``run_id`` and
                ``status``.

        Notes:
            Only a **failed** run raises a notification. A successful run
            rewrites calendars that everybody can see, and telling three
            managers about every routine weekly run would train them to ignore
            the badge — which is what makes them miss the failure that matters.
        """
        run_id = envelope.string_field("run_id")
        status = envelope.string_field("status")
        if status != "failed":
            self.logger.debug(
                "Planning run %s finished as %s; nobody needs telling.",
                run_id,
                status,
            )
            return
        async with self._manager.session() as session:
            service = self._notifications(session)
            await service.notify_supervisors(
                company_id=None,
                kind=NotificationKind.PLANNING_COMPLETED,
                title="Échec du calcul de planning",
                body=(
                    f"Le calcul de planning {run_id} a échoué. Les plannings "
                    f"existants n'ont pas été modifiés."
                ),
            )

    async def close(self) -> None:
        """Release the broker connection and the database pool."""
        await self.publisher.close()
        await self._manager.disconnect()

    ############################
    # Internal Helpers Methods #
    ############################

    def _notifications(self, session) -> NotificationService:
        """Build a notification service over a session.

        Args:
            session: The open database session.

        Returns:
            NotificationService: The service.
        """
        return NotificationService(
            notifications=NotificationRepository(session=session, logger=self.logger),
            users=UserRepository(session=session, logger=self.logger),
            logger=self.logger,
        )

    async def _notify_author(
        self,
        envelope: EventEnvelope,
        kind: NotificationKind,
        title_template: str,
        body_template: str,
    ) -> None:
        """Tell the author of a quote about a decision on it.

        Args:
            envelope (EventEnvelope): The message.
            kind (NotificationKind): What the notification is about.
            title_template (str): Title, with a ``{reference}`` placeholder.
            body_template (str): Body, with a ``{reference}`` placeholder.

        Notes:
            A quote with no recorded author produces nothing. Those exist —
            every quote written before authorship was recorded — and there is
            nobody to tell about them.
        """
        author_id = envelope.string_field("author_id")
        if author_id is None:
            self.logger.info(
                "Quote %s has no recorded author; nobody to tell.",
                envelope.string_field("quote_id"),
            )
            return
        reference = envelope.string_field("reference") or "?"
        async with self._manager.session() as session:
            service = self._notifications(session)
            await service.notify_account(
                recipient_id=author_id,
                kind=kind,
                title=title_template.format(reference=reference),
                body=body_template.format(reference=reference),
                quote_id=envelope.string_field("quote_id"),
            )
