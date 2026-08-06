from __future__ import annotations

# Standard library imports
from contextlib import asynccontextmanager
from functools import lru_cache
from logging import Logger, getLogger
from typing import AsyncIterator, Optional

# Third-party imports
from fastapi import Depends, HTTPException, Request, status
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from api.sse.broadcaster import NotificationBroadcaster
from models.auth.user import User
from models.configuration.app_config import AppConfig
from models.enums import PlanningRunStatus, UserRole
from service.auth.auth import AuthService
from service.companies.companies import CompanyService
from service.companies.registration import CompanyRegistrationService
from service.customers.customers import CustomerService
from service.emails.emails import EmailService
from service.hcas.hcas import HcaService
from service.intervention_types.intervention_types import InterventionTypeService
from service.messaging.publisher import EventPublisher
from service.notifications.notifications import NotificationService
from service.planning.interventions import InterventionService
from service.planning.plannings import PlanningService
from service.quotes.quotes import QuoteService
from storage.db.connection_manager import DatabaseConnectionManager
from storage.repositories.company import CompanyRepository
from storage.repositories.customer import CustomerRepository
from storage.repositories.hca import HcaRepository
from storage.repositories.hca_application import HcaApplicationRepository
from storage.repositories.intervention import InterventionRepository
from storage.repositories.intervention_type import InterventionTypeRepository
from storage.repositories.notification import NotificationRepository
from storage.repositories.planning_run import PlanningRunRepository
from storage.repositories.planning_settings import PlanningSettingsRepository
from storage.repositories.quote import QuoteRepository
from storage.repositories.user import UserRepository
from storage.s3.s3_storage import S3Storage

logger: Logger = getLogger(__name__)

_connection_manager: Optional[DatabaseConnectionManager] = None
# One per process, holding the event streams this instance is serving. It
# cannot be request-scoped: a stream outlives the request that opened it, and
# the whole point is that a later request can push into it.
_notification_broadcaster: NotificationBroadcaster = NotificationBroadcaster(
    logger=logger
)
# Also process-wide, and for the same reason: it holds a broker connection that
# must be shared and reused rather than opened per request. Built on first use
# rather than at import, because the configuration is not loaded yet here.
_event_publisher: Optional[EventPublisher] = None


@lru_cache
def get_app_config() -> AppConfig:
    """Return the validated application configuration.

    Returns:
        AppConfig: The configuration, loaded once per process.

    Notes:
        Cached because the configuration is immutable for the process's
        lifetime and re-reading the file on every request would be pure waste.

        Which file is loaded is :class:`AppConfig`'s decision, driven by
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
        One transaction per request, not per repository call. A handler that
        writes to several tables therefore either lands entirely or not at all.

        The session is published on ``request.state`` so
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
    return UserRepository(session=session, logger=logger)


async def get_hca_repository(
    session: AsyncSession = Depends(get_session),
) -> HcaRepository:
    """Return the assistant repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        HcaRepository: The repository.
    """
    return HcaRepository(session=session, logger=logger)


async def get_customer_repository(
    session: AsyncSession = Depends(get_session),
) -> CustomerRepository:
    """Return the customer repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        CustomerRepository: The repository.
    """
    return CustomerRepository(session=session, logger=logger)


async def get_intervention_type_repository(
    session: AsyncSession = Depends(get_session),
) -> InterventionTypeRepository:
    """Return the intervention-type repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        InterventionTypeRepository: The repository.
    """
    return InterventionTypeRepository(session=session, logger=logger)


async def get_intervention_type_service(
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
) -> InterventionTypeService:
    """Return the intervention-type catalog service.

    Args:
        types (InterventionTypeRepository): The catalog store.

    Returns:
        InterventionTypeService: The service.
    """
    return InterventionTypeService(types=types, logger=logger)


async def get_quote_repository(
    session: AsyncSession = Depends(get_session),
) -> QuoteRepository:
    """Return the quote repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        QuoteRepository: The repository.
    """
    return QuoteRepository(session=session, logger=logger)


async def get_quote_service(
    quotes: QuoteRepository = Depends(get_quote_repository),
    types: InterventionTypeRepository = Depends(get_intervention_type_repository),
) -> QuoteService:
    """Return the quote service.

    Args:
        quotes (QuoteRepository): The quote store.
        types (InterventionTypeRepository): The catalog store.

    Returns:
        QuoteService: The service.
    """
    return QuoteService(
        quotes=quotes,
        types=types,
        config=get_app_config().pricing,
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
    return NotificationRepository(session=session, logger=logger)


async def get_notification_service(
    notifications: NotificationRepository = Depends(get_notification_repository),
    users: UserRepository = Depends(get_user_repository),
) -> NotificationService:
    """Return the notification service.

    Args:
        notifications (NotificationRepository): The notification store.
        users (UserRepository): The account store, used to resolve recipients.

    Returns:
        NotificationService: The service.
    """
    return NotificationService(notifications=notifications, users=users, logger=logger)


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
        _event_publisher = EventPublisher(
            config=get_app_config().rabbitmq, logger=logger
        )
    return _event_publisher


def get_notification_broadcaster() -> NotificationBroadcaster:
    """Return the process-wide event-stream fan-out.

    Returns:
        NotificationBroadcaster: The broadcaster holding this instance's open
        streams.

    Notes:
        Not a ``lru_cache``-d factory but a module-level instance, because it
        holds live state rather than configuration. Two callers must get the
        *same* object or a push would go to a broadcaster nobody is reading.
    """
    return _notification_broadcaster


async def get_customer_service(
    customers: CustomerRepository = Depends(get_customer_repository),
    quotes: QuoteRepository = Depends(get_quote_repository),
) -> CustomerService:
    """Return the customer service.

    Args:
        customers (CustomerRepository): The customer store.
        quotes (QuoteRepository): The quote store, consulted before a delete.

    Returns:
        CustomerService: The service.
    """
    return CustomerService(customers=customers, quotes=quotes, logger=logger)


@lru_cache
def get_photo_storage() -> S3Storage:
    """Return the object store holding assistant photographs.

    Returns:
        S3Storage: The store, shared across requests.

    Notes:
        Cached because the underlying boto3 client owns a connection pool.
        Building one per request would defeat it and re-resolve credentials
        every time.
    """
    return S3Storage(config=get_app_config().s3, logger=logger)


@lru_cache
def get_email_service() -> EmailService:
    """Return the outbound email service.

    Returns:
        EmailService: The service, configured from the application settings.

    Notes:
        Cached like the object store: it holds configuration and opens a
        connection per message, so there is nothing per-request about it.
    """
    return EmailService(config=get_app_config().email, logger=logger)


async def get_hca_service(
    hcas: HcaRepository = Depends(get_hca_repository),
) -> HcaService:
    """Return the assistant service.

    Args:
        hcas (HcaRepository): The assistant store.

    Returns:
        HcaService: The service, photograph handling included.
    """
    return HcaService(hcas=hcas, photos=get_photo_storage(), logger=logger)


async def get_planning_run_repository(
    session: AsyncSession = Depends(get_session),
) -> PlanningRunRepository:
    """Return the planning-run repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        PlanningRunRepository: The repository.
    """
    return PlanningRunRepository(session=session, logger=logger)


async def get_intervention_repository(
    session: AsyncSession = Depends(get_session),
) -> InterventionRepository:
    """Return the intervention repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        InterventionRepository: The repository.
    """
    return InterventionRepository(session=session, logger=logger)


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
    return PlanningSettingsRepository(session=session, logger=logger)


async def get_planning_service(
    runs: PlanningRunRepository = Depends(get_planning_run_repository),
    interventions: InterventionRepository = Depends(get_intervention_repository),
    quotes: QuoteRepository = Depends(get_quote_repository),
    customers: CustomerRepository = Depends(get_customer_repository),
    hcas: HcaRepository = Depends(get_hca_repository),
    settings: PlanningSettingsRepository = Depends(get_planning_settings_repository),
) -> PlanningService:
    """Return the planning service.

    Args:
        runs (PlanningRunRepository): The run records.
        interventions (InterventionRepository): The scheduled visits.
        quotes (QuoteRepository): The accepted work.
        customers (CustomerRepository): Where the work happens.
        hcas (HcaRepository): The workforce.
        settings (PlanningSettingsRepository): The store holding the
            manager-owned planning rules.

    Returns:
        PlanningService: The service.
    """
    return PlanningService(
        runs=runs,
        interventions=interventions,
        quotes=quotes,
        customers=customers,
        hcas=hcas,
        settings=settings,
        config=get_app_config().planning,
        logger=logger,
    )


async def run_planning_job(run_id: str) -> None:
    """Execute a planning run outside the request that asked for it.

    Args:
        run_id (str): The run to execute.

    Notes:
        Built by hand rather than through ``Depends`` because a background task
        outlives its request. The request-scoped session is committed and
        returned to the pool as soon as the 202 is written, so reusing it here
        would work on a closed connection.

        Nothing is raised out of this. A background task's exception has
        nowhere to go — the client already holds its 202 — so a failure is
        recorded on the run itself, which is what the caller polls.
    """
    logger.info("Starting the background planning run %s.", run_id)
    manager = await get_connection_manager()
    try:
        async with manager.session() as session:
            service = PlanningService(
                runs=PlanningRunRepository(session=session, logger=logger),
                interventions=InterventionRepository(session=session, logger=logger),
                quotes=QuoteRepository(session=session, logger=logger),
                customers=CustomerRepository(session=session, logger=logger),
                hcas=HcaRepository(session=session, logger=logger),
                settings=PlanningSettingsRepository(session=session, logger=logger),
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
        This is what makes the dispatch automatic: computing a planning is the
        event, and the webhook is how it is announced. Pointing the configured
        URL at this application's own endpoint is the ordinary arrangement —
        the emails then go out through a normal request, with the same
        handlers and logging as anything else.

        A failure here is logged and swallowed. The planning itself succeeded
        and is already stored; an unreachable webhook must not turn a good run
        into a failed one, and the run can be dispatched again by calling the
        endpoint by hand.
    """
    config = get_app_config().webhook
    if not config.enabled:
        logger.debug("The planning webhook is disabled; not announcing %s.", run_id)
        return
    token = config.get_token()
    if not token:
        logger.warning(
            "Not announcing planning run %s: the webhook secret (%s) is unset.",
            run_id,
            config.token_env,
        )
        return
    logger.info("Announcing planning run %s to %s.", run_id, config.url)
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.post(
                config.url,
                json={"run_id": run_id},
                headers={"X-Webhook-Token": token},
            )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Could not announce planning run %s: %s", run_id, exc)
        return
    logger.info(
        "Planning run %s announced; the webhook answered %d.",
        run_id,
        response.status_code,
    )


async def get_company_repository(
    session: AsyncSession = Depends(get_session),
) -> CompanyRepository:
    """Return the company repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        CompanyRepository: The repository.
    """
    return CompanyRepository(session=session, logger=logger)


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
    return CompanyService(companies=companies, users=users, hcas=hcas, logger=logger)


async def get_hca_application_repository(
    session: AsyncSession = Depends(get_session),
) -> HcaApplicationRepository:
    """Return the application repository.

    Args:
        session (AsyncSession): The request-scoped session.

    Returns:
        HcaApplicationRepository: The repository.
    """
    return HcaApplicationRepository(session=session, logger=logger)


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
        photos=get_photo_storage(),
        applications=applications,
        companies=companies,
        users=users,
        auth=AuthService(
            users=users, hcas=hcas, config=get_app_config().auth, logger=logger
        ),
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
        AuthService: The service.
    """
    return AuthService(
        users=users,
        hcas=hcas,
        config=get_app_config().auth,
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
        Middleware runs before FastAPI resolves dependencies, so it cannot use
        ``Depends``. This builds the same object by hand.

        **A context manager, not a plain factory.** The session has to be
        closed when the token lookup finishes: every request carrying a bearer
        token passes through here, and a session left to the garbage collector
        holds its pooled connection until then. Under any real load that
        exhausts the pool, and the symptom — requests hanging on connection
        checkout — points nowhere near the middleware.

        The session is closed around the lookup rather than shared with the
        request's own. The middleware only reads, and holding a connection for
        the whole request, including the time the handler spends working, is
        the same exhaustion by a slower route.
    """
    manager = await get_connection_manager()
    factory = manager.get_session_factory()
    async with factory() as session:
        yield AuthService(
            users=UserRepository(session=session, logger=logger),
            hcas=HcaRepository(session=session, logger=logger),
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
            "Unauthenticated request to %s %s.", request.method, request.url.path
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


def get_manager_user(request: Request) -> User:
    """Return the account, requiring manager privileges or above.

    Args:
        request (Request): The incoming request.

    Returns:
        User: The authenticated account.

    Raises:
        HTTPException: 401 when unauthenticated, 403 when the account ranks
            below manager.
    """
    user = get_current_user(request)
    if not user.role.has_at_least(UserRole.MANAGER):
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
