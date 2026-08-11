from __future__ import annotations

# Standard library imports
import asyncio
from datetime import UTC, datetime
from logging import Logger, getLogger
import signal
from typing import ClassVar, List, Optional

# Third-party imports
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.configuration.app_config import AppConfig
from models.enums import (
    BillingRunStatus,
    EventRoutingKey,
    NotificationKind,
    PlanningRunStatus,
    WorkerRole,
)
from models.messaging.event_envelope import EventEnvelope
from models.notifications.notification import Notification
from service.billing.billings import BillingService
from service.billing.webhook import BillingWebhook
from service.messaging.consumer import EventConsumer
from service.messaging.publisher import EventPublisher
from service.observability.metrics import ApplicationMetrics
from service.observability.probe_server import ProbeServer
from service.planning.plannings import PlanningService
from service.planning.webhook import PlanningWebhook
from storage.db.connection_manager import DatabaseConnectionManager
from storage.repositories.auth.user import UserRepository
from storage.repositories.billing.bill import BillRepository
from storage.repositories.billing.billing_run import BillingRunRepository
from storage.repositories.billing.billing_settings import (
    BillingSettingsRepository,
)
from storage.repositories.catalog.intervention_type import (
    InterventionTypeRepository,  # noqa: E501
)
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.notifications.notification import (
    NotificationRepository,  # noqa: E501
)
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.people.hca import HcaRepository
from storage.repositories.planning.intervention import InterventionRepository
from storage.repositories.planning.planning_run import PlanningRunRepository
from storage.repositories.planning.planning_settings import (
    PlanningSettingsRepository,  # noqa: E501
)
from storage.repositories.quoting.quote import QuoteRepository
from storage.s3.s3_storage import S3Storage


class WorkerRunner:
    """The worker: what it consumes, and what it does when a message arrives.

    Attributes:
        PLANNING_QUEUE (ClassVar[str]): Base name of the planning queue.
        NOTIFICATION_QUEUE (ClassVar[str]): Base name of the notification
            queue.
        BILLING_QUEUE (ClassVar[str]): Base name of the billing queue.
        NOTIFICATION_KEYS (ClassVar[tuple]): The topics the notification queue
            binds.
        config (AppConfig): The whole application configuration.
        publisher (EventPublisher): Announces finished runs and written
            notifications.
        webhook (PlanningWebhook): Announces a finished run to the dispatcher.
        billing_webhook (BillingWebhook): Announces an approved invoice to
            whatever emails it.
        manager (DatabaseConnectionManager): The pool every handler draws its
            session from.
        planning (EventConsumer): Consumer for the planning queues.
        notifications (EventConsumer): Consumer for the notification queues.
        billing (EventConsumer): Consumer for the billing queues.
        lifecycle (EventConsumer): Consumer for ``company.created``.
        logger (Logger): Logger for the worker's lifecycle and its handlers.

    Notes:
        - **A queue per agency per kind of work.** The planning solve pins a
          core for thirty seconds; sharing a queue with the notification
          fan-out would leave a manager waiting half a minute to be told a
          quote needs looking at. Billing is a third shape again — I/O-bound
          but long, since a monthly close renders and uploads one document per
          customer — so it gets its own queue rather than parking a month's
          work at the head of either of the others. Splitting again by agency
          means one agency's backlog or poison message is its own, rather than
          something every
          other agency waits behind.
        - The agencies are enumerated once at startup and then kept current by
          the ``company.created`` announcement, so an agency founded through
          self-registration is served without a restart. The enumeration is
          what makes the announcement queue safe to be non-durable: anything
          missed while this process was down is picked up next time it starts.
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
        - The notification worker also answers ``skill.added``, which is the
          one topic here raised by a *subordinate* rather than by the quote
          workflow or the solver. A skill is declared without approval and
          takes effect at once, so telling the supervisors is what makes that
          safe — see :meth:`skill_added`.
        - **Recipients are resolved here, from roles, rather than named by the
          message.** The thing publishing an event knows that a quote was
          submitted; it does not know who in the agency is allowed to rule on
          it, and it should not have to. A payload that named its own
          recipients would be a way to send a notification to anybody.
        - Fan-out failures are never fatal to the event that caused them. A
          quote is submitted whether or not the notification lands; refusing the
          submission because nobody could be told would be a worse outcome than
          a manager finding it in the queue unprompted.
        - One class rather than a runner delegating to a handler object. The
          two halves need each other in both directions — the handlers write
          through the pool the runner opens, and the ``company.created``
          handler binds the queues the runner consumes — and splitting them
          bought nothing but a callback the runner had to hand back to the
          handlers so they could reach it.
    """

    PLANNING_QUEUE: ClassVar[str] = "planning-runs"
    NOTIFICATION_QUEUE: ClassVar[str] = "quote-notifications"
    BILLING_QUEUE: ClassVar[str] = "billing-runs"
    NOTIFICATION_KEYS: ClassVar[tuple] = (
        EventRoutingKey.QUOTE_SUBMITTED,
        EventRoutingKey.QUOTE_VALIDATED,
        EventRoutingKey.QUOTE_REFUSED,
        EventRoutingKey.PLANNING_RUN_COMPLETED,
        EventRoutingKey.SKILL_ADDED,
        EventRoutingKey.BILLING_RUN_COMPLETED,
        EventRoutingKey.BILL_ACCEPTED,
    )

    def __init__(
        self,
        config: AppConfig,
        role: WorkerRole = WorkerRole.PLANNING,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the runner.

        Args:
            config (AppConfig): The application configuration.
            role (WorkerRole): What this process consumes. Defaults to
                :attr:`~models.enums.WorkerRole.PLANNING`.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            Every consumer is constructed whatever the role, and only the one
            this process serves is ever started. Building them conditionally
            would put a ``None`` behind every attribute and a check in front of
            every use; an unstarted consumer holds no connection and costs
            nothing.
        """
        self.config = config
        self.role = role
        self.logger = logger if logger else getLogger(__name__)
        self.publisher = EventPublisher(config=config.rabbitmq)
        self.webhook = PlanningWebhook(config=config.webhook)
        self.billing_webhook = BillingWebhook(config=config.billing_webhook)
        self.manager = DatabaseConnectionManager(config=config.database)
        self.metrics = ApplicationMetrics(logger=self.logger)
        self.planning = EventConsumer(
            config=config.rabbitmq,
            metrics=self.metrics,
            role=role.value,
            logger=self.logger,
        )
        self.notifications = EventConsumer(
            config=config.rabbitmq,
            metrics=self.metrics,
            role=role.value,
            logger=self.logger,
        )
        self.billing = EventConsumer(
            config=config.rabbitmq,
            metrics=self.metrics,
            role=role.value,
            logger=self.logger,
        )
        self.lifecycle = EventConsumer(
            config=config.rabbitmq,
            metrics=self.metrics,
            role="lifecycle",
            logger=self.logger,
        )
        self.probes = ProbeServer(
            config=config.observability.named(f"worker-{role.value}"),
            metrics=self.metrics,
            is_ready=self.is_ready,
            logger=self.logger,
        )
        self.logger.debug("WorkerRunner created for the %s role.", role.value)

    ############################
    # Internal Helpers Methods #
    ############################

    def _register_handlers(self) -> None:
        """Wire this role's topics to the coroutines that answer them.

        Notes:
            - Only this role's handlers are registered. A consumer with no handler
              for a routing key logs and acknowledges the message rather than
              answering it, so registering both roles' handlers on a process that
              consumes one queue would be harmless — but it would also make the
              code read as though either process might do either job.
            - ``company.created`` is registered whatever the role. Both roles have
              queues of their own to declare when an agency is founded.
        """
        if self.role is WorkerRole.PLANNING:
            self.planning.on(EventRoutingKey.PLANNING_RUN_REQUESTED, self.run_planning)  # noqa: E501
        elif self.role is WorkerRole.BILLING:
            self.billing.on(EventRoutingKey.BILLING_RUN_REQUESTED, self.run_billing)
        else:
            self.notifications.on(EventRoutingKey.QUOTE_SUBMITTED, self.quote_submitted)  # noqa: E501
            self.notifications.on(EventRoutingKey.QUOTE_VALIDATED, self.quote_validated)  # noqa: E501
            self.notifications.on(EventRoutingKey.QUOTE_REFUSED, self.quote_refused)
            self.notifications.on(
                EventRoutingKey.PLANNING_RUN_COMPLETED, self.planning_completed
            )
            self.notifications.on(EventRoutingKey.SKILL_ADDED, self.skill_added)
            self.notifications.on(
                EventRoutingKey.BILLING_RUN_COMPLETED, self.billing_completed
            )
            self.notifications.on(EventRoutingKey.BILL_ACCEPTED, self.bill_accepted)
        self.lifecycle.on(EventRoutingKey.COMPANY_CREATED, self.company_created)  # noqa: E501

    def _billing_service(self, session: AsyncSession) -> BillingService:
        """Build the billing service over one session.

        Args:
            session (AsyncSession): The session the run's writes go through.

        Returns:
            BillingService: The service.

        Notes:
            Assembled here by hand rather than taken from the API's dependency
            module, because the worker must never import ``api``. That is also
            why :class:`~service.billing.webhook.BillingWebhook` lives in
            ``service``.
        """
        return BillingService(
            bills=BillRepository(session=session),
            runs=BillingRunRepository(session=session),
            settings=BillingSettingsRepository(session=session),
            quotes=QuoteRepository(session=session),
            interventions=InterventionRepository(session=session),
            customers=CustomerRepository(session=session),
            companies=CompanyRepository(session=session),
            config=self.config.billing,
            documents=S3Storage(config=self.config.s3, logger=self.logger),
            logger=self.logger,
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

    def _utc_now(self) -> datetime:
        """Return the current instant as timezone-aware UTC.

        Returns:
            datetime: The current instant in UTC.
        """
        return datetime.now(UTC)

    async def _notify_supervisors(
        self,
        session: AsyncSession,
        company_id: Optional[str],
        kind: NotificationKind,
        title: str,
        body: Optional[str] = None,
        quote_id: Optional[str] = None,
    ) -> List[str]:
        """Tell every manager and administrator of an agency.

        Args:
            session (AsyncSession): The open database session.
            company_id (Optional[str]): The agency whose supervisors to tell.
            kind (NotificationKind): What the notification is about.
            title (str): The one-line summary.
            body (Optional[str]): The detail.
            quote_id (Optional[str]): The quote it points at.

        Returns:
            List[str]: The accounts written to, for the announcement that
            follows.

        Notes:
            - **A fan-out with no agency writes nothing.** The account store
              reads a missing agency as "every supervisor of every agency",
              which is how a message that lost its ``company_id`` — one written
              by an older publisher, say — would put a badge on every manager on
              the platform, naming work they have no access to. There is no
              notification worth sending to everybody, so the absence is
              refused here rather than interpreted.
            - An agency with no active supervisor is logged at ``ERROR`` and
              produces nothing. It is a real operational fault — work is piling
              up with nobody able to release it — and it deserves to be loud
              rather than to look like a quiet day.
        """
        if not company_id:
            self.logger.error(
                "Cannot fan %r out: the message named no agency, and there is "
                "no notification worth sending to every agency at once.",
                title,
            )
            return []
        users = UserRepository(session=session)
        supervisors = await users.list_supervisors(company_id)
        if not supervisors:
            self.logger.error(
                "Nobody to notify about %r: company %s has no active manager "
                "or administrator.",
                title,
                company_id,
            )
            return []
        now = self._utc_now()
        pending = [
            Notification(
                recipient_id=supervisor.id,
                kind=kind,
                title=title,
                body=body,
                quote_id=quote_id,
                created_at=now,
            )
            for supervisor in supervisors
            if supervisor.id is not None
        ]
        repository = NotificationRepository(session=session)
        written = await repository.create_many(pending)
        self.logger.info(
            "Notified %d supervisor(s) of company %s: %s.",
            len(written),
            company_id,
            title,
        )
        return [notification.recipient_id for notification in written]

    async def _notify_account(
        self,
        session: AsyncSession,
        recipient_id: str,
        kind: NotificationKind,
        title: str,
        body: Optional[str] = None,
        quote_id: Optional[str] = None,
    ) -> List[str]:
        """Tell one account.

        Args:
            session (AsyncSession): The open database session.
            recipient_id (str): The account to tell.
            kind (NotificationKind): What the notification is about.
            title (str): The one-line summary.
            body (Optional[str]): The detail.
            quote_id (Optional[str]): The quote it points at.

        Returns:
            List[str]: The account written to, or empty when none was named.

        Notes:
            Used for the return leg of the quote workflow — telling an assistant
            that the quote they submitted was approved or sent back. A quote
            whose author is unknown produces nothing rather than failing: it was
            written before authorship was recorded, and that is not the
            assistant's problem to be told about.
        """
        if not recipient_id:
            self.logger.warning("Cannot deliver %r: no recipient was named.", title)  # noqa: E501
            return []
        repository = NotificationRepository(session=session)  # noqa: E501
        written = await repository.create(
            Notification(
                recipient_id=recipient_id,
                kind=kind,
                title=title,
                body=body,
                quote_id=quote_id,
                created_at=self._utc_now(),
            )
        )
        self.logger.info("Notified %s: %s.", recipient_id, title)
        return [written.recipient_id]

    async def _announce(self, company_id: Optional[str], recipients: List[str]) -> None:  # noqa: E501
        """Tell the API which accounts have something new to read.

        Args:
            company_id (Optional[str]): The agency the notifications belong to.
            recipients (List[str]): The accounts written to.

        Notes:
            - Published **after** the session that wrote the rows has closed and
              committed. An API instance that read the notification list on the
              strength of this message must find the rows already there;
              announcing first is how a badge comes to count something that is
              not yet visible.
            - Only identifiers travel. Each API instance holds its own open
              streams and wakes the ones it has; the reader then fetches over
              HTTP, from the same endpoint it would have used had the push never
              arrived. That is what keeps the database the single source of
              truth and a lost message a matter of latency.
            - Nothing is published for an empty recipient list, and nothing is
              published without an agency: the routing key is scoped to one, and
              a notification nobody can be told about is not worth a message.
        """
        if not recipients:
            self.logger.debug("Nothing was written; there is nobody to wake.")
            return
        if not company_id:
            self.logger.error(
                "Wrote %d notification(s) with no agency to announce them "
                "under; the readers will find them on their next fetch.",
                len(recipients),
            )
            return
        await self.publisher.publish(
            EventRoutingKey.NOTIFICATION_CREATED,
            company_id,
            {"recipient_ids": recipients},
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
        async with self.manager.session() as session:
            recipients = await self._notify_account(
                session,
                recipient_id=author_id,
                kind=kind,
                title=title_template.format(reference=reference),
                body=body_template.format(reference=reference),
                quote_id=envelope.string_field("quote_id"),
            )
        await self._announce(envelope.string_field("company_id"), recipients)

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
        async with self.manager.session() as session:
            service = PlanningService(
                runs=PlanningRunRepository(session=session),
                interventions=InterventionRepository(session=session),
                quotes=QuoteRepository(session=session),
                customers=CustomerRepository(session=session),  # noqa: E501
                hcas=HcaRepository(session=session),
                types=InterventionTypeRepository(session=session),
                settings=PlanningSettingsRepository(session=session),
                config=self.config.planning,
                metrics=self.metrics,
                logger=self.logger,
            )
            run = await service.execute_run(run_id)
        self.logger.info("Planning run %s finished as %s.", run_id, run.status.value)  # noqa: E501
        company_id = envelope.string_field("company_id")
        if not company_id:
            self.logger.error(
                "Planning run %s carried no agency; its completion cannot be "
                "announced to one and is dropped.",
                run_id,
            )
            return
        await self.publisher.publish(
            EventRoutingKey.PLANNING_RUN_COMPLETED,
            company_id,
            {"run_id": run_id, "status": run.status.value, "company_id": company_id},  # noqa: E501
        )

    async def run_billing(self, envelope: EventEnvelope) -> None:
        """Generate the invoices for a period the API asked to bill.

        Args:
            envelope (EventEnvelope): The message, carrying ``run_id`` and
                ``company_id``.

        Raises:
            Exception: Whatever the generation raises, so the message is
                dead-lettered and the failure is visible.

        Notes:
            - **This role's whole job**, and the reason it is a role. A monthly
              close over three hundred customers is three hundred documents
              rendered and three hundred objects uploaded — minutes of I/O-bound
              work. On the notifications queue it would sit at the head for that
              whole time and every quote badge would wait behind it; on the
              planning queue it would contend with a CPU-pinned solve and
              inherit a replica count scaled for one.
            - The session is opened here and closed before the completion is
              published, exactly as :meth:`run_planning` does: the announcement
              must find the invoices already committed.
            - **Nothing is emailed.** Every invoice is written waiting for a
              manager; validation is what sends it.
        """
        run_id = envelope.string_field("run_id")
        if run_id is None:
            self.logger.error("A billing message named no run; discarding it.")
            return
        self.logger.info("Generating the invoices of billing run %s.", run_id)
        async with self.manager.session() as session:
            service = self._billing_service(session)
            run = await service.execute_run(run_id)
        self.logger.info(
            "Billing run %s finished as %s with %d invoice(s).",
            run_id,
            run.status.value,
            run.bill_count(),
        )
        company_id = envelope.string_field("company_id")
        if not company_id:
            self.logger.error(
                "Billing run %s carried no agency; its completion cannot be "
                "announced to one and is dropped.",
                run_id,
            )
            return
        await self.publisher.publish(
            EventRoutingKey.BILLING_RUN_COMPLETED,
            company_id,
            {
                "run_id": run_id,
                "status": run.status.value,
                "company_id": company_id,
                "bill_count": run.bill_count(),
            },
        )

    async def billing_completed(self, envelope: EventEnvelope) -> None:
        """Tell the supervisors that a period has invoices to validate.

        Args:
            envelope (EventEnvelope): The message, carrying ``run_id``,
                ``status``, ``company_id`` and ``bill_count``.

        Notes:
            - **Unlike a planning run, a successful one is announced.** A
              planning rewrites calendars everybody can see, so a routine
              success needs no badge. A billing run leaves invoices nobody has
              approved and nothing has been sent from — a run nobody hears about
              is a month quietly unbilled, which is the failure the notification
              exists to prevent.
            - Nothing is emailed to a customer here. This tells the agency it
              has work to do; the customer hears from the bill-accepted webhook,
              after a manager approves each invoice.
            - Told to **that agency's** supervisors, named by the message, for
              the reason the planning notification is: a badge on every other
              agency's managers naming a run they cannot open is noise they
              learn to ignore.
        """
        run_id = envelope.string_field("run_id")
        status = envelope.string_field("status")
        company_id = envelope.string_field("company_id")
        count = envelope.string_field("bill_count") or "0"
        if status == BillingRunStatus.FAILED.value:
            title = "Échec de la facturation"
            body = (
                f"La génération des factures {run_id} a échoué. Aucune facture "
                f"n'a été émise pour cette période."
            )
        else:
            title = "Factures à valider"
            body = (
                f"{count} facture(s) ont été générées et attendent votre "
                f"validation. Rien n'a encore été envoyé aux bénéficiaires."
            )
        async with self.manager.session() as session:
            recipients = await self._notify_supervisors(
                session,
                company_id=company_id,
                kind=NotificationKind.BILLS_TO_VALIDATE,
                title=title,
                body=body,
            )
        await self._announce(company_id, recipients)

    async def bill_accepted(self, envelope: EventEnvelope) -> None:
        """Send an invoice a manager has just approved.

        Args:
            envelope (EventEnvelope): The message, carrying ``bill_id``.

        Notes:
            **This is the step that reaches a customer.** The announcement is
            handed to the webhook, which fetches the stored document and emails
            it — the same arrangement the planning dispatch has, and for the
            same reason: the sending runs as an ordinary authenticated request
            with the handlers and logging every other request has, rather than
            inside a worker nobody can see into.
        """
        bill_id = envelope.string_field("bill_id")
        if bill_id is None:
            self.logger.error(
                "A bill-accepted message named no invoice; discarding it."
            )
            return
        self.logger.info("Invoice %s was approved; announcing it.", bill_id)
        await self.billing_webhook.announce(bill_id)

    async def quote_submitted(self, envelope: EventEnvelope) -> None:
        """Tell the agency's supervisors that a quote needs validating.

        Args:
            envelope (EventEnvelope): The message, carrying ``quote_id``,
                ``reference``, ``company_id`` and ``author_name``.
        """
        quote_id = envelope.string_field("quote_id")
        reference = envelope.string_field("reference") or "?"
        author = envelope.string_field("author_name") or "un intervenant"
        company_id = envelope.string_field("company_id")
        async with self.manager.session() as session:
            recipients = await self._notify_supervisors(
                session,
                company_id=company_id,
                kind=NotificationKind.QUOTE_SUBMITTED,
                title=f"Devis {reference} à valider",
                body=f"{author} a soumis le devis {reference} pour validation.",
                quote_id=quote_id,
            )
        await self._announce(company_id, recipients)

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
            envelope (EventEnvelope): The message, carrying ``run_id``,
                ``status`` and ``company_id``.

        Notes:
            - Only a **failed** run raises a notification. A successful run
              rewrites calendars that everybody can see, and telling three
              managers about every routine weekly run would train them to
              ignore the badge — which is what makes them miss the failure that
              matters.
            - A **succeeded** run is announced to the dispatcher instead, which
              is what emails every assistant their diary and every customer
              their quote. That call used to be made only by the API's
              in-process planning path, and the dev stack does not use it — the
              worker executes the runs. So a planning could succeed, the
              calendars fill, and not one document ever go out, with nothing
              logged to say so.
            - The failure is told to **that agency's** supervisors, named by the
              message. It read as every supervisor on the platform until the
              agency was carried in the payload: a failure in one agency put a
              badge on every other agency's managers, naming a run they have no
              access to.
        """
        run_id = envelope.string_field("run_id")
        status = envelope.string_field("status")
        if status != "failed":
            self.logger.debug(
                "Planning run %s finished as %s; nobody needs telling.",
                run_id,
                status,
            )
            if status == PlanningRunStatus.SUCCEEDED.value:
                await self.webhook.announce(run_id)
            return
        company_id = envelope.string_field("company_id")
        async with self.manager.session() as session:
            recipients = await self._notify_supervisors(
                session,
                company_id=company_id,
                kind=NotificationKind.PLANNING_COMPLETED,
                title="Échec du calcul de planning",
                body=(
                    f"Le calcul de planning {run_id} a échoué. Les plannings "
                    f"existants n'ont pas été modifiés."
                ),
            )
        await self._announce(company_id, recipients)

    async def skill_added(self, envelope: EventEnvelope) -> None:
        """Tell the agency's supervisors that an assistant declared a skill.

        Args:
            envelope (EventEnvelope): The message, carrying ``hca_id``,
                ``hca_name``, ``skill_name``, ``skill_code`` and ``company_id``.

        Notes:
            - **This is the whole reason a declaration needs no approval.** A
              skill takes effect the moment its owner enters it, which is what
              stops the agency losing track of who can do what; the safeguard
              is that every manager and administrator is told, and any of them
              can withdraw it before the next planning run acts on it.
            - The notification carries no ``quote_id`` — there is no quote — so
              :meth:`~models.notifications.Notification.is_actionable` reports
              it as plain text rather than a link. That is why
              :meth:`~models.enums.NotificationKind.concerns_a_quote` had to
              stop being written as "not the planning one": a skill
              notification rendered as a link would be a dead one.
            - The body names the code as well as the label, because the code is
              what a requirement is matched on. A supervisor deciding whether
              somebody has over-claimed needs to know which requirement the
              declaration just satisfied, and the free-text name does not say.
        """
        hca_name = envelope.string_field("hca_name") or "un intervenant"
        skill_name = envelope.string_field("skill_name") or "une compétence"
        skill_code = envelope.string_field("skill_code")
        company_id = envelope.string_field("company_id")
        described = f"{skill_name} ({skill_code})" if skill_code else skill_name
        if skill_code is None:
            self.logger.warning(
                "%s declared %r with no catalogue code; no requirement can match it.",
                hca_name,
                skill_name,
            )
        async with self.manager.session() as session:
            recipients = await self._notify_supervisors(
                session,
                company_id=company_id,
                kind=NotificationKind.SKILL_ADDED,
                title=f"Nouvelle compétence déclarée par {hca_name}",
                body=(
                    f"{hca_name} a déclaré la compétence {described}. Elle sera "
                    f"prise en compte au prochain calcul de planning."
                ),
            )
        await self._announce(company_id, recipients)

    async def company_created(self, envelope: EventEnvelope) -> None:
        """Bind the queues of an agency that has just been founded.

        Args:
            envelope (EventEnvelope): The message, carrying ``company_id``.

        Notes:
            Without this a self-registered agency would have no queues until
            the next restart: its quotes would be published under a routing key
            nothing is bound to, and no notification would ever be written. The
            symptom is an agency where the product silently does half its job,
            which is why the announcement exists at all.
        """
        company_id = envelope.string_field("company_id")
        if not company_id:
            self.logger.error("A company.created message named no agency.")
            return
        self.logger.info("Agency %s was founded; binding its queues.", company_id)  # noqa: E501
        await self.serve(company_id)

    async def companies(self) -> List[str]:
        """Return every agency this worker should be serving.

        Returns:
            List[str]: The identifiers of every stored agency.

        Notes:
            Read at startup so a worker that was down while agencies were
            founded catches up, which is what lets the ``company.created``
            queue be exclusive and non-durable.
        """
        async with self.manager.session() as session:
            repository = CompanyRepository(session=session)
            stored = await repository.list(size=None)
        identifiers = [company.id for company in stored if company.id]
        self.logger.info("Worker will serve %d agency/agencies.", len(identifiers))  # noqa: E501
        return identifiers

    async def serve(self, company_id: str) -> None:
        """Bind and consume one agency's queues.

        Args:
            company_id (str): The agency to serve.

        Notes:
            - Idempotent, because declaring a queue that already exists is. That
              matters: a restart racing a ``company.created`` announcement can
              reach the same agency twice, and the safe ordering below relies on
              being able to.
            - **Only this role's queue is bound.** The other one is declared by
              the other deployment, and a process that bound both would consume
              from a queue it has no handler for — quietly acknowledging every
              message on it and dropping the work.
        """
        if self.role is WorkerRole.PLANNING:
            await self.planning.consume_for_company(
                self.PLANNING_QUEUE,
                [EventRoutingKey.PLANNING_RUN_REQUESTED],
                company_id,
            )
            return
        if self.role is WorkerRole.BILLING:
            await self.billing.consume_for_company(
                self.BILLING_QUEUE,
                [EventRoutingKey.BILLING_RUN_REQUESTED],
                company_id,
            )
            return
        await self.notifications.consume_for_company(
            self.NOTIFICATION_QUEUE,
            list(self.NOTIFICATION_KEYS),
            company_id,
        )

    def is_ready(self) -> bool:
        """Return whether this worker can currently do its job.

        Returns:
            bool: ``True`` when its own consumer holds an open connection.

        Notes:
            - **The broker, not the process.** A worker whose process is running
              but whose connection has gone consumes nothing; reporting it Ready
              is what lets a rolling update replace the last working replica with
              one that cannot consume, and nothing surfaces until a queue stops
              draining.
            - The role's own consumer is the one asked. The other holds no
              connection by design, so checking both would report every worker
              unready for ever.
        """
        consumers = {
            WorkerRole.PLANNING: self.planning,
            WorkerRole.NOTIFICATIONS: self.notifications,
            WorkerRole.BILLING: self.billing,
        }
        connection = consumers[self.role].connection
        return connection is not None and not connection.is_closed

    async def start(self) -> List[str]:
        """Connect, bind every agency, and begin consuming.

        Returns:
            List[str]: The agencies now being served.

        Notes:
            - The pool is opened **before any consumer is started**, so no
              message can be delivered to a handler that has no database behind
              it. ``session()`` asks the manager for its factory and refuses
              when there is none; without this every handler raises
              ``MTDatabaseNotConnected`` and every message is dead-lettered —
              the worker looks healthy, consumes steadily, and writes nothing at
              all, which is a far quieter failure than not starting would have
              been.
            - The announcement queue is bound **before** the agencies are
              enumerated, not after. An agency founded between the enumeration
              and the binding would otherwise fall through the gap: too late to
              be listed, too early to be announced. Overlapping the two is safe
              because :meth:`serve` is idempotent; leaving a gap is not.
        """
        await self.manager.connect()
        self.logger.info("The worker is connected to the database.")
        self._register_handlers()
        if self.role is WorkerRole.PLANNING:
            await self.planning.start()
        elif self.role is WorkerRole.BILLING:
            await self.billing.start()
        else:
            await self.notifications.start()
        await self.lifecycle.start()

        await self.lifecycle.consume_every_company([EventRoutingKey.COMPANY_CREATED])  # noqa: E501
        served = await self.companies()
        for company_id in served:
            await self.serve(company_id)
        await self.probes.start()
        self.logger.info(
            "The %s worker is consuming %d agency/agencies; waiting for messages.",
            self.role.value,
            len(served),
        )
        return served

    async def run(self) -> None:
        """Start, then consume until the process is asked to stop."""
        await self.start()
        await self._wait_for_a_signal()
        self.logger.info("Worker is shutting down.")
        await self.close()

    async def close(self) -> None:
        """Release every broker connection and the database pool."""
        await self.probes.close()
        await self.lifecycle.close()
        await self.planning.close()
        await self.notifications.close()
        await self.billing.close()
        await self.publisher.close()
        await self.manager.disconnect()
