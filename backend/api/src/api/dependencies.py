from __future__ import annotations

# Standard library imports
from contextlib import asynccontextmanager
from functools import lru_cache
from logging import Logger, getLogger
from typing import AsyncIterator, Optional

# Third-party imports
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from api.sse.streams import NotificationStreams
from models.auth.user import User
from models.configuration.app_config import AppConfig
from models.enums import EventRoutingKey, PlanningRunStatus, UserRole
from service.auth.auth import AuthService
from service.billing.billings import BillingService
from service.billing.webhook import BillingWebhook
from service.certifications.certifications import CertificationTypeService
from service.companies.companies import CompanyService
from service.companies.registration import CompanyRegistrationService
from service.customers.customers import CustomerService
from service.customers.portal import CustomerPortalService
from service.emails.emails import EmailService
from service.hcas.hcas import HcaService
from service.integrations.invoicing import InvoicingService
from service.integrations.utils.factur_x import FacturXBuilder
from service.intervention_types.intervention_types import (
    InterventionTypeService,
)
from service.messaging.consumer import EventConsumer
from service.messaging.publisher import EventPublisher
from service.observability.metrics import ApplicationMetrics
from service.organisation.agencies import AgencyService
from service.organisation.team_documents import TeamDocumentService
from service.organisation.teams import TeamService
from service.planning.interventions import InterventionService
from service.planning.plannings import PlanningService
from service.planning.webhook import PlanningWebhook
from service.quotes.documents import QuoteDocumentService
from service.quotes.quotes import QuoteService
from service.security.credential_cipher import CredentialCipher
from service.skills.skills import SkillTypeService
from service.utils.invoice_renderer import InvoiceRenderer
from service.utils.quote_renderer import QuoteRenderer
from storage.db.connection_manager import DatabaseConnectionManager
from storage.repositories.auth.user import UserRepository
from storage.repositories.billing.bill import BillRepository
from storage.repositories.billing.billing_run import BillingRunRepository
from storage.repositories.billing.billing_settings import (
    BillingSettingsRepository,
)
from storage.repositories.catalog.certification_type import (
    CertificationTypeRepository,  # noqa: E501
)
from storage.repositories.catalog.intervention_type import (
    InterventionTypeRepository,  # noqa: E501
)
from storage.repositories.catalog.skill_type import SkillTypeRepository
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.integrations.einvoicing_integration import (
    EInvoicingIntegrationRepository,
)
from storage.repositories.notifications.notification import (
    NotificationRepository,  # noqa: E501
)
from storage.repositories.organisation.agency import AgencyRepository
from storage.repositories.organisation.team import TeamRepository
from storage.repositories.organisation.team_document import (
    TeamDocumentRepository,  # noqa: E501
)
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.people.hca import HcaRepository
from storage.repositories.people.hca_application import (
    HcaApplicationRepository,  # noqa: E501
)
from storage.repositories.planning.intervention import InterventionRepository
from storage.repositories.planning.planning_run import PlanningRunRepository
from storage.repositories.planning.planning_settings import (
    PlanningSettingsRepository,  # noqa: E501
)
from storage.repositories.quoting.quote import QuoteRepository
from storage.s3.s3_storage import S3Storage

logger: Logger = getLogger(__name__)

_connection_manager: Optional[DatabaseConnectionManager] = None
_notification_streams: NotificationStreams = NotificationStreams(logger=logger)
_event_publisher: Optional[EventPublisher] = None
_notification_consumer: Optional[EventConsumer] = None


@lru_cache
def get_metrics() -> ApplicationMetrics:
    """Return this API instance's metrics registry.

    Returns:
        ApplicationMetrics: The registry, built once per process.

    Notes:
        **Cached, and that is load-bearing.** A registry per request would
        declare the same metric names again on every call and raise a
        duplicate-timeseries error on the second one — and the figures a
        registry holds are cumulative, so even if it did not raise, a fresh one
        per request would report zero for everything, for ever.
    """
    return ApplicationMetrics()


@lru_cache
def get_app_config() -> AppConfig:
    """Return the validated application configuration.

    Returns:
        AppConfig: The configuration, loaded once per process.

    Notes:
        - Cached because the configuration is immutable for the process's
          lifetime and re-reading the file on every request would be pure waste.
        - Which file is loaded is :class:`AppConfig`'s decision, driven by
          ``$SIMPLE_ERP_CONFIG``; the Alembic environment loads the same way, so the
          schema and the running application can never come from different
          configurations.
    """
    logger.debug("Loading the application configuration.")
    return AppConfig.load()


async def get_connection_manager() -> DatabaseConnectionManager:
    """Return the process-wide database connection manager.

    Returns:
        DatabaseConnectionManager: The manager, connected on first use.

    Notes:
        A module-level singleton rather than a per-request object: the engine
        owns a connection pool, and building one per request would defeat it
        entirely.
    """
    global _connection_manager
    if _connection_manager is None:
        logger.info("Creating the database connection manager.")
        _connection_manager = DatabaseConnectionManager(
            config=get_app_config().database,
            logger=logger,
        )
    if not _connection_manager.is_connected:
        await _connection_manager.connect()
    return _connection_manager


async def close_connection_manager() -> None:
    """Dispose of the connection manager, if one was created.

    Notes:
        Called from the application's shutdown hook so the pool is released
        cleanly rather than torn down with the process.
    """
    global _connection_manager
    if _connection_manager is None:
        logger.debug("No connection manager to close.")
        return
    await _connection_manager.disconnect()
    _connection_manager = None


async def get_session(
    request: Request,
    manager: DatabaseConnectionManager = Depends(get_connection_manager),
) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session inside a transaction.

    Args:
        request (Request): The incoming request, which the session is attached
            to.
        manager (DatabaseConnectionManager): The connection manager.

    Yields:
        AsyncSession: A session committed when the request succeeds and rolled
        back when it raises.

    Notes:
        - One transaction per request, not per repository call. A handler that
          writes to several tables therefore either lands entirely or not at all.
        - The session is published on ``request.state`` so
          :class:`TransactionMiddleware` can commit it *before* the response is
          written. This teardown still commits, but FastAPI runs it after the
          response has been sent — too late for a client that immediately reads
          back what it just wrote.
    """
    async with manager.session() as session:
        request.state.session = session
        yield session


async def get_user_repository(
    session: AsyncSession = Depends(get_session),
) -> UserRepository:
    """Return the account repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        UserRepository: The repository.
    """
    return UserRepository(session=session)


async def get_hca_repository(
    session: AsyncSession = Depends(get_session),
) -> HcaRepository:
    """Return the assistant repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        HcaRepository: The repository.
    """
    return HcaRepository(session=session)


async def get_customer_repository(
    session: AsyncSession = Depends(get_session),
) -> CustomerRepository:
    """Return the customer repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        CustomerRepository: The repository.
    """
    return CustomerRepository(session=session)


async def get_intervention_type_repository(
    session: AsyncSession = Depends(get_session),
) -> InterventionTypeRepository:
    """Return the intervention-type repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        InterventionTypeRepository: The repository.
    """
    return InterventionTypeRepository(session=session)


async def get_certification_type_repository(
    session: AsyncSession = Depends(get_session),
) -> CertificationTypeRepository:
    """Return the certification-catalogue repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        CertificationTypeRepository: The repository.
    """
    return CertificationTypeRepository(session=session)


async def get_certification_type_service(
    certifications: CertificationTypeRepository = Depends(
        get_certification_type_repository
    ),
    hcas: HcaRepository = Depends(get_hca_repository),
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
) -> CertificationTypeService:
    """Return the certification-catalogue service.

    Args:
        certifications (CertificationTypeRepository): The catalogue store.
        hcas (HcaRepository): The workforce, consulted before a delete.
        types (InterventionTypeRepository): The service catalogue, consulted
            before a delete.

    Returns:
        CertificationTypeService: The service.

    Notes:
        It takes three repositories because nothing in the database enforces
        the references to a certification code: they live in a JSON array and
        in a nullable column, so refusing to strand one means counting the rows
        that name it.
    """
    return CertificationTypeService(
        certifications=certifications,
        hcas=hcas,
        types=types,
        logger=logger,
    )


async def get_skill_type_repository(
    session: AsyncSession = Depends(get_session),
) -> SkillTypeRepository:
    """Return the skill-catalogue repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        SkillTypeRepository: The repository.
    """
    return SkillTypeRepository(session=session)


async def get_skill_type_service(
    skills: SkillTypeRepository = Depends(get_skill_type_repository),
    hcas: HcaRepository = Depends(get_hca_repository),
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
) -> SkillTypeService:
    """Return the skill-catalogue service.

    Args:
        skills (SkillTypeRepository): The catalogue store.
        hcas (HcaRepository): The workforce, consulted before a delete.
        types (InterventionTypeRepository): The service catalogue, consulted
            before a delete.

    Returns:
        SkillTypeService: The service.

    Notes:
        Three repositories, for the same reason its certification twin takes
        three: nothing in the database enforces the references to a skill code,
        so refusing to strand one means counting the rows that name it.
    """
    return SkillTypeService(
        skills=skills,
        hcas=hcas,
        types=types,
        logger=logger,
    )


async def get_intervention_type_service(
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
    certifications: CertificationTypeService = Depends(get_certification_type_service),
    skills: SkillTypeService = Depends(get_skill_type_service),
) -> InterventionTypeService:
    """Return the intervention-type catalog service.

    Args:
        types (InterventionTypeRepository): The catalog store.
        certifications (CertificationTypeService): The certification
            catalogue, consulted before a requirement is stored.
        skills (SkillTypeService): The skill catalogue, consulted the same way.

    Returns:
        InterventionTypeService: The service.
    """
    return InterventionTypeService(
        types=types, certifications=certifications, skills=skills
    )


async def get_quote_repository(
    session: AsyncSession = Depends(get_session),
) -> QuoteRepository:
    """Return the quote repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        QuoteRepository: The repository.
    """
    return QuoteRepository(session=session)


async def get_agency_repository(
    session: AsyncSession = Depends(get_session),
) -> AgencyRepository:
    """Return the site repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        AgencyRepository: The repository.
    """
    return AgencyRepository(session=session)


async def get_team_repository(
    session: AsyncSession = Depends(get_session),
) -> TeamRepository:
    """Return the team repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        TeamRepository: The repository.
    """
    return TeamRepository(session=session)


async def get_team_document_repository(
    session: AsyncSession = Depends(get_session),
) -> TeamDocumentRepository:
    """Return the teamspace document repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        TeamDocumentRepository: The repository.
    """
    return TeamDocumentRepository(session=session)


async def get_team_service(
    teams: TeamRepository = Depends(get_team_repository),
    agencies: AgencyRepository = Depends(get_agency_repository),
    users: UserRepository = Depends(get_user_repository),
    quotes: QuoteRepository = Depends(get_quote_repository),
) -> TeamService:
    """Return the team service.

    Args:
        teams (TeamRepository): Reads and writes the teams.
        agencies (AgencyRepository): Proves a member works at the team's site.
        users (UserRepository): Proves the named manager may run one.
        quotes (QuoteRepository): The busyness tie-break, and the refusal to
            disband a team that still holds work.

    Returns:
        TeamService: The service.

    Notes:
        Four repositories, and none of them optional: the attribution rule reads
        sites for distance and quotes for load, and both are what make one team
        rather than another the answer.
    """
    return TeamService(teams=teams, agencies=agencies, users=users, quotes=quotes)


async def get_quote_service(
    quotes: QuoteRepository = Depends(get_quote_repository),
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
    teams: TeamService = Depends(get_team_service),
    customers: CustomerRepository = Depends(get_customer_repository),
    certifications: CertificationTypeService = Depends(get_certification_type_service),
    skills: SkillTypeService = Depends(get_skill_type_service),
) -> QuoteService:
    """Return the quote service.

    Args:
        quotes (QuoteRepository): The quote store.
        types (InterventionTypeRepository): The catalog store.
        teams (TeamService): Decides which team a new quote belongs to, and
            which teams the caller may move one between.
        customers (CustomerRepository): Read for the household's coordinate,
            which is what "the closest team" is measured from.
        certifications (CertificationTypeService): The certification
            catalogue, consulted before a line's requirement override is
            stored.
        skills (SkillTypeService): The skill catalogue, consulted the same way.

    Returns:
        QuoteService: The service.

    Notes:
        The team service is resolved through the same request-scoped session as
        everything else here, so the attribution read and the quote write happen
        inside one transaction. A team formed by a concurrent request is either
        wholly visible to the attribution or wholly absent from it.
    """
    return QuoteService(
        quotes=quotes,
        types=types,
        teams=teams,
        customers=customers,
        config=get_app_config().pricing,
        certifications=certifications,
        skills=skills,
        logger=logger,
    )


async def get_notification_repository(
    session: AsyncSession = Depends(get_session),
) -> NotificationRepository:
    """Return the notification repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        NotificationRepository: The repository.
    """
    return NotificationRepository(session=session)


def get_event_publisher() -> EventPublisher:
    """Return the process-wide broker publisher.

    Returns:
        EventPublisher: The publisher, holding this process's connection.

    Notes:
        A module-level instance rather than a per-request one. Opening an AMQP
        connection costs a round trip and a channel; doing it per request would
        make publishing an event more expensive than the work that caused it.
    """
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher(config=get_app_config().rabbitmq)
    return _event_publisher


def get_notification_streams() -> NotificationStreams:
    """Return the process-wide registry of open event streams.

    Returns:
        NotificationStreams: The registry holding this instance's open streams.

    Notes:
        Not a ``lru_cache``-d factory but a module-level instance, because it
        holds live state rather than configuration. Two callers must get the
        *same* object or a wake-up would go to a registry nobody is reading.
    """
    return _notification_streams


async def start_notification_relay() -> None:
    """Begin turning ``notification.created`` messages into stream wake-ups.

    Notes:
        - **Best effort, unlike the worker's consumer.** A worker with no broker
          has nothing to do and fails loudly so its supervisor restarts it. An
          API with no broker still answers every request, including the one that
          lists the notifications this would have announced — so a broker that
          is down or disabled costs the live push and nothing else. Refusing to
          start would turn a degraded convenience into an outage.
        - The queue is **exclusive and server-named**, so every API instance
          gets its own copy of every announcement. That is required, not
          incidental: each instance holds different open streams, and a shared
          durable queue would hand each message to one instance while the
          readers connected to the others were never woken.
        - Disabled is the default configuration, which is what keeps a laptop
          and the test suite from needing a broker at all.
    """
    global _notification_consumer
    config = get_app_config()
    if not config.rabbitmq.enabled:
        logger.info("The broker is disabled. Notifications will not be pushed.")
        return
    consumer = EventConsumer(config=config.rabbitmq)
    consumer.on(EventRoutingKey.NOTIFICATION_CREATED, get_notification_streams().relay)
    try:
        await consumer.start()
        await consumer.consume_every_company([EventRoutingKey.NOTIFICATION_CREATED])
    except Exception as exc:  # noqa: BLE001 - the API must still serve
        logger.error(
            "Could not consume %s; readers will see notifications on their "
            "next fetch rather than immediately: %s.",
            EventRoutingKey.NOTIFICATION_CREATED.value,
            exc,
        )
        return
    _notification_consumer = consumer
    logger.info("Notifications written by the worker will be pushed to readers.")


async def stop_notification_relay() -> None:
    """Release the relay's broker connection, if one was opened.

    Notes:
        Called from the application's shutdown hook. Closing is best-effort for
        the same reason the publisher's is: a process on its way out must not
        hang on a broker that has already gone.
    """
    global _notification_consumer
    if _notification_consumer is None:
        logger.debug("No notification relay to close.")
        return
    await _notification_consumer.close()
    _notification_consumer = None


async def get_customer_service(
    customers: CustomerRepository = Depends(get_customer_repository),
    quotes: QuoteRepository = Depends(get_quote_repository),
    users: UserRepository = Depends(get_user_repository),
) -> CustomerService:
    """Return the customer service.

    Args:
        customers (CustomerRepository): The customer store.
        quotes (QuoteRepository): The quote store, consulted before a delete.
        users (UserRepository): The account store, so deleting a household
            takes their portal account with them. The foreign key is
            ``RESTRICT``, so without it the delete fails at the database.

    Returns:
        CustomerService: The service.
    """
    return CustomerService(customers=customers, quotes=quotes, users=users)


@lru_cache
def get_object_storage() -> S3Storage:
    """Return the object store holding photographs and company logos.

    Returns:
        S3Storage: The store, shared across requests.

    Notes:
        - Cached because the underlying boto3 client owns a connection pool.
          Building one per request would defeat it and re-resolve credentials
          every time.
        - One store for both kinds of image. They live under separate key
          prefixes but in the same bucket with the same credentials, so a second
          provider would be a second connection pool to the same place.
    """
    return S3Storage(config=get_app_config().s3)


@lru_cache
def get_email_service() -> EmailService:
    """Return the outbound email service.

    Returns:
        EmailService: The service, configured from the application settings.

    Notes:
        Cached like the object store: it holds configuration and opens a
        connection per message, so there is nothing per-request about it.
    """
    return EmailService(config=get_app_config().email, logos=get_object_storage())


async def get_hca_service(
    hcas: HcaRepository = Depends(get_hca_repository),
) -> HcaService:
    """Return the assistant service.

    Args:
        hcas (HcaRepository): The assistant store.

    Returns:
        HcaService: The service, photograph handling included.
    """
    return HcaService(hcas=hcas, photos=get_object_storage())


async def get_planning_run_repository(
    session: AsyncSession = Depends(get_session),
) -> PlanningRunRepository:
    """Return the planning-run repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        PlanningRunRepository: The repository.
    """
    return PlanningRunRepository(session=session)


async def get_intervention_repository(
    session: AsyncSession = Depends(get_session),
) -> InterventionRepository:
    """Return the intervention repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        InterventionRepository: The repository.
    """
    return InterventionRepository(session=session)


async def get_intervention_service(
    interventions: InterventionRepository = Depends(get_intervention_repository),
    quotes: QuoteService = Depends(get_quote_service),
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
) -> InterventionService:
    """Return the service that edits one scheduled visit.

    Args:
        interventions (InterventionRepository): The scheduled visits.
        quotes (QuoteService): Prices and stores the paperwork.
        types (InterventionTypeRepository): The catalog the rates come from.

    Returns:
        InterventionService: The service.
    """
    return InterventionService(
        interventions=interventions,
        quotes=quotes,
        types=types,
        logger=logger,
    )


async def get_planning_settings_repository(
    session: AsyncSession = Depends(get_session),
) -> PlanningSettingsRepository:
    """Return the planning-settings repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        PlanningSettingsRepository: The repository.
    """
    return PlanningSettingsRepository(session=session)


async def get_planning_service(
    runs: PlanningRunRepository = Depends(get_planning_run_repository),
    interventions: InterventionRepository = Depends(get_intervention_repository),
    quotes: QuoteRepository = Depends(get_quote_repository),
    customers: CustomerRepository = Depends(get_customer_repository),
    hcas: HcaRepository = Depends(get_hca_repository),
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
    settings: PlanningSettingsRepository = Depends(get_planning_settings_repository),
    teams: TeamService = Depends(get_team_service),
) -> PlanningService:
    """Return the planning service.

    Args:
        runs (PlanningRunRepository): The run records.
        interventions (InterventionRepository): The scheduled visits.
        quotes (QuoteRepository): The accepted work.
        customers (CustomerRepository): Where the work happens.
        hcas (HcaRepository): The workforce.
        types (InterventionTypeRepository): The service catalogue, read for the
            qualifications each kind of work requires.
        settings (PlanningSettingsRepository): The store holding the
            manager-owned planning rules.
        teams (TeamService): Whose members a run may schedule, and which teams
            a caller may ask for a planning of.

    Returns:
        PlanningService: The service.

    Notes:
        The team service is what makes a run *a team's* run: it supplies both
        the workforce the solver may use and the narrowing that decides whether
        the caller may name that team at all. Injected rather than built here so
        it shares the request's session with everything else.
    """
    return PlanningService(
        runs=runs,
        interventions=interventions,
        quotes=quotes,
        customers=customers,
        hcas=hcas,
        types=types,
        settings=settings,
        teams=teams,
        config=get_app_config().planning,
        logger=logger,
    )


async def run_planning_job(run_id: str) -> None:
    """Execute a planning run outside the request that asked for it.

    Args:
        run_id (str): The run to execute.

    Notes:
        - Built by hand rather than through ``Depends`` because a background task
          outlives its request. The request-scoped session is committed and
          returned to the pool as soon as the 202 is written, so reusing it here
          would work on a closed connection.
        - Nothing is raised out of this. A background task's exception has
          nowhere to go — the client already holds its 202 — so a failure is
          recorded on the run itself, which is what the caller polls.
    """
    logger.info("Starting the background planning run %s.", run_id)
    manager = await get_connection_manager()
    try:
        async with manager.session() as session:
            service = PlanningService(
                runs=PlanningRunRepository(session=session),
                interventions=InterventionRepository(session=session),
                quotes=QuoteRepository(session=session),
                customers=CustomerRepository(session=session),
                hcas=HcaRepository(session=session),
                types=InterventionTypeRepository(session=session),
                settings=PlanningSettingsRepository(session=session),
                teams=TeamService(
                    teams=TeamRepository(session=session),
                    agencies=AgencyRepository(session=session),
                    users=UserRepository(session=session),
                    quotes=QuoteRepository(session=session),
                    logger=logger,
                ),
                config=get_app_config().planning,
                logger=logger,
            )
            run = await service.execute_run(run_id)
        logger.info("Background planning run %s finished as %s.", run_id, run.status)
        if run.status is PlanningRunStatus.SUCCEEDED:
            await notify_planning_completed(run_id)
    except Exception as exc:  # noqa: BLE001 - a background task has no caller
        logger.error("Background planning run %s could not run: %s", run_id, exc)


async def notify_planning_completed(run_id: str) -> None:
    """Call the webhook that emails a finished planning.

    Args:
        run_id (str): The run that succeeded.

    Notes:
        The call itself lives in
        :class:`~service.planning.webhook.PlanningWebhook`, because the worker
        finishes runs too and cannot import this module. This wrapper stays so
        the in-process planning path reads the same as it did.
    """
    await PlanningWebhook(config=get_app_config().webhook).announce(run_id)


async def get_company_repository(
    session: AsyncSession = Depends(get_session),
) -> CompanyRepository:
    """Return the company repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        CompanyRepository: The repository.
    """
    return CompanyRepository(session=session)


async def get_company_service(
    companies: CompanyRepository = Depends(get_company_repository),
    users: UserRepository = Depends(get_user_repository),
    hcas: HcaRepository = Depends(get_hca_repository),
) -> CompanyService:
    """Return the company service.

    Args:
        companies (CompanyRepository): The company store.
        users (UserRepository): The account store, to check an agency is empty
            before it is removed.
        hcas (HcaRepository): The assistant store, for the same check.

    Returns:
        CompanyService: The service.
    """
    return CompanyService(
        companies=companies, users=users, hcas=hcas, logos=get_object_storage()
    )


async def get_hca_application_repository(
    session: AsyncSession = Depends(get_session),
) -> HcaApplicationRepository:
    """Return the application repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        HcaApplicationRepository: The repository.
    """
    return HcaApplicationRepository(session=session)


async def get_hca_application_service(
    applications: HcaApplicationRepository = Depends(get_hca_application_repository),
    companies: CompanyRepository = Depends(get_company_repository),
    hcas: HcaRepository = Depends(get_hca_repository),
    users: UserRepository = Depends(get_user_repository),
) -> HcaService:
    """Return the assistant-application service.

    Args:
        applications (HcaApplicationRepository): The application store.
        companies (CompanyRepository): The agencies applied to.
        hcas (HcaRepository): The assistant store.
        users (UserRepository): The account store.

    Returns:
        HcaService: The service.

    Notes:
        Every repository shares the request's session, so approving an
        application writes the assistant and the account in one transaction.
        Half of that pair is a broken state.
    """
    return HcaService(
        hcas=hcas,
        photos=get_object_storage(),
        applications=applications,
        companies=companies,
        users=users,
        auth=AuthService(users=users, hcas=hcas, config=get_app_config().auth),
        logger=logger,
    )


async def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    hcas: HcaRepository = Depends(get_hca_repository),
) -> AuthService:
    """Return the authentication service.

    Args:
        users (UserRepository): The account store.
        hcas (HcaRepository): The assistant store.

    Returns:
        AuthService: The service, portrait handling included.

    Notes:
        The object store is passed here and not to
        :func:`get_auth_service_standalone`. This factory serves the routes,
        including the two that replace and remove a portrait; the standalone one
        serves the authentication middleware, which only resolves tokens and has
        no business holding a bucket client.
    """
    return AuthService(
        users=users,
        hcas=hcas,
        config=get_app_config().auth,
        photos=get_object_storage(),
        logger=logger,
    )


async def get_company_registration_service(
    companies: CompanyService = Depends(get_company_service),
    auth: AuthService = Depends(get_auth_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    config: AppConfig = Depends(get_app_config),
) -> CompanyRegistrationService:
    """Return the company-registration service.

    Args:
        companies (CompanyService): The company service.
        auth (AuthService): The authentication service.
        publisher (EventPublisher): The broker publisher, to announce the
            agency so the workers bind its queues.
        config (AppConfig): The application configuration, for the flag.

    Returns:
        CompanyRegistrationService: The service.
    """
    return CompanyRegistrationService(
        companies=companies,
        auth=auth,
        publisher=publisher,
        config=config.auth,
        logger=logger,
    )


@asynccontextmanager
async def get_auth_service_standalone() -> AsyncIterator[AuthService]:
    """Build an authentication service outside the dependency graph.

    Yields:
        AuthService: A service bound to its own short-lived session.

    Notes:
        - Middleware runs before FastAPI resolves dependencies, so it cannot use
          ``Depends``. This builds the same object by hand.
        - **A context manager, not a plain factory.** The session has to be
          closed when the token lookup finishes: every request carrying a bearer
          token passes through here, and a session left to the garbage collector
          holds its pooled connection until then. Under any real load that
          exhausts the pool, and the symptom — requests hanging on connection
          checkout — points nowhere near the middleware.
        - The session is closed around the lookup rather than shared with the
          request's own. The middleware only reads, and holding a connection for
          the whole request, including the time the handler spends working, is
          the same exhaustion by a slower route.
    """
    manager = await get_connection_manager()
    factory = manager.get_session_factory()
    async with factory() as session:
        yield AuthService(
            users=UserRepository(session=session),
            hcas=HcaRepository(session=session),
            config=get_app_config().auth,
            logger=logger,
        )


def get_current_user(request: Request) -> User:
    """Return the account the request is authenticated as.

    Args:
        request (Request): The incoming request.

    Returns:
        User: The authenticated account.

    Raises:
        HTTPException: 401 when the request carries no valid credential.

    Notes:
        The account is attached to the request by the authentication
        middleware; this only reads it. Written as a plain synchronous function
        taking the request — rather than a chain of ``Depends`` — so it can be
        unit-tested against a stub request with no application at all.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        logger.warning(
            "Unauthenticated request to %s %s.",
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_hca_user(request: Request) -> User:
    """Return the account, requiring it to be an assistant's.

    Args:
        request (Request): The incoming request.

    Returns:
        User: The authenticated assistant account.

    Raises:
        HTTPException: 401 when unauthenticated, 403 when the account is not an
            assistant's.

    Notes:
        Compared by identity, not by rank: a manager outranks an assistant but
        has no assistant record, so "at least an assistant" would be the wrong
        question for a route that reads one.
    """
    user = get_current_user(request)
    if user.role is not UserRole.HCA:
        logger.warning(
            "Account %s (%s) is not an assistant; denied %s %s.",
            user.id,
            user.role.value,
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is reserved for home care assistants.",
        )
    return user


def get_customer_user(request: Request) -> User:
    """Return the account, requiring it to be a customer's.

    Args:
        request (Request): The incoming request.

    Returns:
        User: The authenticated customer account.

    Raises:
        HTTPException: 401 when unauthenticated, 403 when the account is not a
            customer's.

    Notes:
        - **Compared by identity, and it cannot be anything else.** A customer
          is not a rung of the staff ladder — see
          :meth:`~models.enums.UserRole.rank`, which refuses to rank one — so
          there is no "at least a customer" to ask. Written the usual way with
          ``has_at_least`` this would raise; written the *forgiving* way it
          would admit every employee to a household's private space.
        - The account's ``customer_id`` is guaranteed present by the model, so
          every route behind this guard may resolve the household from the
          credential and never from a path parameter.
    """
    user = get_current_user(request)
    logger.debug("Checking customer access for account %s.", user.id)
    if user.role is not UserRole.CUSTOMER:
        logger.warning(
            "Account %s (%s) is not a customer; denied %s %s.",
            user.id,
            user.role.value,
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is reserved for customers.",
        )
    if user.customer_id is None:
        logger.error(
            "Customer account %s carries no customer link; access refused.", user.id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not linked to a customer record.",
        )
    logger.info("Customer account %s admitted to the portal.", user.id)
    return user


def get_manager_user(request: Request) -> User:
    """Return the account, requiring manager privileges or above.

    Args:
        request (Request): The incoming request.

    Returns:
        User: The authenticated account.

    Raises:
        HTTPException: 401 when unauthenticated, 403 when the account ranks
            below manager or is not staff at all.

    Notes:
        **The staff test comes first, and it is not defensive tidiness.**
        ``has_at_least`` ranks, and :meth:`~models.enums.UserRole.rank` refuses
        to rank a customer — so calling it on one raises ``MTRoleNotRankable``,
        which the handler map turns into a **422 carrying the enum's internal
        explanation**. A household reaching a staff route would be told their
        request was malformed, in a message about ladders. It is a 403: they
        are authenticated, the request is fine, and they may not do this.
    """
    user = get_current_user(request)
    if not user.role.is_staff() or not user.role.has_at_least(UserRole.MANAGER):
        logger.warning(
            "Account %s (%s) is below manager; denied %s %s.",
            user.id,
            user.role.value,
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires manager privileges.",
        )
    logger.debug("Manager gate passed for account %s.", user.id)
    return user


async def get_bill_repository(
    session: AsyncSession = Depends(get_session),
) -> BillRepository:
    """Return the invoice repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        BillRepository: The repository.
    """
    return BillRepository(session=session)


async def get_billing_run_repository(
    session: AsyncSession = Depends(get_session),
) -> BillingRunRepository:
    """Return the billing-run repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        BillingRunRepository: The repository.
    """
    return BillingRunRepository(session=session)


async def get_billing_settings_repository(
    session: AsyncSession = Depends(get_session),
) -> BillingSettingsRepository:
    """Return the billing-settings repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        BillingSettingsRepository: The repository.
    """
    return BillingSettingsRepository(session=session)


@lru_cache
def get_factur_x_builder() -> FacturXBuilder:
    """Return the builder that writes an invoice as a Factur-X document.

    Returns:
        FacturXBuilder: The builder, built once per process.

    Notes:
        Cached like the renderer, and for the same reason: it holds only
        constants and a logger, and rebuilding it per request would allocate a
        namespace table on every invoice.
    """
    return FacturXBuilder()


@lru_cache
def get_invoice_renderer() -> InvoiceRenderer:
    """Return the renderer that lays an invoice out as a PDF.

    Returns:
        InvoiceRenderer: The renderer, built once per process.

    Notes:
        Cached because it is stateless and its stylesheet is worth building
        once, the same reason :func:`get_object_storage` is cached. It holds no
        session and no request-scoped state.
    """
    return InvoiceRenderer(logger=logger)


async def get_billing_service(
    bills: BillRepository = Depends(get_bill_repository),
    runs: BillingRunRepository = Depends(get_billing_run_repository),
    settings: BillingSettingsRepository = Depends(get_billing_settings_repository),
    quotes: QuoteRepository = Depends(get_quote_repository),
    interventions: InterventionRepository = Depends(get_intervention_repository),
    customers: CustomerRepository = Depends(get_customer_repository),
    companies: CompanyRepository = Depends(get_company_repository),
) -> BillingService:
    """Return the billing service.

    Args:
        bills (BillRepository): Where invoices are stored.
        runs (BillingRunRepository): Where generation runs are recorded.
        settings (BillingSettingsRepository): The agency's invoicing rules.
        quotes (QuoteRepository): Where the prices come from.
        interventions (InterventionRepository): Where the delivered hours come
            from.
        customers (CustomerRepository): Who invoices are addressed to.
        companies (CompanyRepository): Who issues them.

    Returns:
        BillingService: The service.

    Notes:
        The object store is the same one that holds photographs and logos —
        same bucket, same credentials — but invoices are written under their own
        prefix with their own cache headers and are never handed to a browser.
    """
    return BillingService(
        bills=bills,
        runs=runs,
        settings=settings,
        quotes=quotes,
        interventions=interventions,
        customers=customers,
        companies=companies,
        config=get_app_config().billing,
        documents=get_object_storage(),
        renderer=get_invoice_renderer(),
        factur_x=get_factur_x_builder(),
        logger=logger,
    )


def get_billing_webhook() -> BillingWebhook:
    """Return the announcer that sends a validated invoice.

    Returns:
        BillingWebhook: The announcer.

    Notes:
        Built per call rather than cached: it holds only its configuration, and
        the configuration object is already cached behind
        :func:`get_app_config`.
    """
    return BillingWebhook(config=get_app_config().billing_webhook, logger=logger)


def get_admin_user(request: Request) -> User:
    """Return the account, requiring administrator privileges.

    Args:
        request (Request): The incoming request.

    Returns:
        User: The authenticated account.

    Raises:
        HTTPException: 401 when unauthenticated, 403 when the account is not an
            administrator.
    """
    user = get_current_user(request)
    if not user.is_admin():
        logger.warning(
            "Account %s (%s) is not an administrator; denied %s %s.",
            user.id,
            user.role.value,
            request.method,
            request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges are required.",
        )
    logger.debug("Admin gate passed for account %s.", user.id)
    return user


async def get_quote_document_service(
    quotes: QuoteService = Depends(get_quote_service),
    customers: CustomerRepository = Depends(get_customer_repository),
    companies: CompanyRepository = Depends(get_company_repository),
) -> QuoteDocumentService:
    """Return the quote document service.

    Args:
        quotes (QuoteService): The quote service.
        customers (CustomerRepository): The customer store.
        companies (CompanyRepository): The agency store.

    Returns:
        QuoteDocumentService: The service.

    Notes:
        The object store is resolved here rather than injected, matching how
        the other document paths reach it, and a deployment without one simply
        prints quotes with no letterhead.
    """
    return QuoteDocumentService(
        quotes=quotes,
        customers=customers,
        companies=companies,
        renderer=QuoteRenderer(),
        logos=get_object_storage(),
    )


async def get_customer_portal_service(
    customers: CustomerService = Depends(get_customer_service),
    interventions: InterventionService = Depends(get_intervention_service),
    quotes: QuoteService = Depends(get_quote_service),
    quote_store: QuoteRepository = Depends(get_quote_repository),
    intervention_store: InterventionRepository = Depends(get_intervention_repository),
    bills: BillingService = Depends(get_billing_service),
    documents: QuoteDocumentService = Depends(get_quote_document_service),
) -> CustomerPortalService:
    """Return the customer portal service.

    Args:
        customers (CustomerService): The customer service.
        interventions (InterventionService): The visit service.
        quotes (QuoteService): The quote service.
        quote_store (QuoteRepository): The quote store, for the status move.
        intervention_store (InterventionRepository): The visit store.
        bills (BillingService): Reads and serves their invoices.
        documents (QuoteDocumentService): Renders a quote as a PDF.

    Returns:
        CustomerPortalService: The service.

    Notes:
        Composed entirely from services that already exist. The portal adds one
        behaviour of its own — a household's change sends the quote back for
        validation — and reuses the cancelling and repricing that the manager's
        calendar already does.
    """
    return CustomerPortalService(
        customers=customers,
        interventions=interventions,
        quotes=quotes,
        quote_store=quote_store,
        intervention_store=intervention_store,
        bills=bills,
        documents=documents,
    )


async def get_einvoicing_integration_repository(
    session: AsyncSession = Depends(get_session),
) -> EInvoicingIntegrationRepository:
    """Return the e-invoicing integration repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        EInvoicingIntegrationRepository: The repository.
    """
    return EInvoicingIntegrationRepository(session=session)


@lru_cache
def get_credential_cipher() -> CredentialCipher:
    """Return the cipher that seals platform credentials.

    Returns:
        CredentialCipher: The cipher, built once per process.

    Notes:
        **Cached, and that is load-bearing.** Deriving the key costs six hundred
        thousand PBKDF2 rounds. Paid once at start-up it is invisible; paid per
        request it would put a third of a second in front of every call that
        touches an integration.

        A deployment whose key is unset or too short raises here, which means it
        raises on the first request rather than at import — deliberate, because
        a process that cannot decrypt a credential should fail where the failure
        is attributable rather than refusing to start for reasons an operator
        has to go digging for.
    """
    return CredentialCipher(get_app_config().integrations)


async def get_invoicing_service(
    integrations: EInvoicingIntegrationRepository = Depends(
        get_einvoicing_integration_repository
    ),
) -> InvoicingService:
    """Return the service that connects a platform and transmits through it.

    Args:
        integrations (EInvoicingIntegrationRepository): Where the connections
            are stored.

    Returns:
        InvoicingService: The service.

    Notes:
        The platform catalogue rides on the configuration this is handed, so a
        deployment that declares a fifth platform in ``app.yaml`` gets a fifth
        card without a code change.
    """
    return InvoicingService(
        integrations=integrations,
        cipher=get_credential_cipher(),
        config=get_app_config().integrations,
    )


async def get_agency_service(
    agencies: AgencyRepository = Depends(get_agency_repository),
    companies: CompanyRepository = Depends(get_company_repository),
    teams: TeamRepository = Depends(get_team_repository),
) -> AgencyService:
    """Return the site service.

    Args:
        agencies (AgencyRepository): Reads and writes the sites.
        companies (CompanyRepository): Read for the legal identity a head office
            inherits.
        teams (TeamRepository): Consulted before a site is removed, and for the
            team count each site carries on screen.

    Returns:
        AgencyService: The service.
    """
    return AgencyService(agencies=agencies, companies=companies, teams=teams)


async def get_team_document_service(
    documents: TeamDocumentRepository = Depends(get_team_document_repository),
    teams: TeamService = Depends(get_team_service),
) -> TeamDocumentService:
    """Return the teamspace service.

    Args:
        documents (TeamDocumentRepository): Indexes the stored objects.
        teams (TeamService): Resolves the team and the caller's membership.

    Returns:
        TeamDocumentService: The service.

    Notes:
        The object store is resolved here rather than injected, matching every
        other document path. A deployment without one answers 503 on the
        teamspace routes and serves the rest of the application unaffected.
    """
    return TeamDocumentService(
        documents=documents, teams=teams, storage=get_object_storage()
    )
