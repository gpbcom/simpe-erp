from __future__ import annotations

# Standard library imports
from contextlib import asynccontextmanager
import logging
from logging.config import dictConfig
import os
from pathlib import Path
from typing import AsyncIterator, Optional

# Third-party imports
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import yaml

# First-party imports
from api.dependencies import (
    close_connection_manager,
    get_app_config,
    get_object_storage,
    start_notification_relay,
    stop_notification_relay,
)
from api.exception_handlers import ExceptionHandlers
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.transaction_middleware import TransactionMiddleware
from api.observability import router as observability_router
from api.v1.auth.accounts import router as accounts_router
from api.v1.bills.settings import router as billing_settings_router
from api.v1.bills.bills import router as bills_router
from api.v1.bills.runs import router as billing_runs_router
from api.v1.auth.auth import router as auth_router
from api.v1.certifications.certifications import (
    router as certifications_router,
)
from api.v1.companies.companies import router as companies_router
from api.v1.customers.customers import router as customers_router
from api.v1.hcas.applications import router as hca_applications_router
from api.v1.hcas.availability import router as availability_router
from api.v1.hcas.hcas import router as hcas_router
from api.v1.hcas.photos import router as hca_photos_router
from api.v1.hcas.skills import router as hca_skills_router
from api.v1.intervention_types.intervention_types import (
    router as intervention_types_router,
)
from api.v1.me.me import router as me_router
from api.v1.notifications.notifications import router as notifications_router
from api.v1.planning.interventions import router as interventions_router
from api.v1.planning.plannings import router as plannings_router
from api.v1.planning.runs import router as planning_runs_router
from api.v1.planning.settings import router as planning_settings_router
from api.v1.quotes.quotes import router as quotes_router
from api.v1.skills.skills import router as skills_router
from api.v1.users.users import router as users_router
from api.v1.webhooks.webhooks import router as webhooks_router
from models.geo.postal_address import PostalAddress

logger = logging.getLogger(__name__)

#: Names the logging configuration to use. A container sets it to
#: ``conf/logger.k8s.yaml``, which writes JSON to stdout and nothing to disk;
#: unset, the colourised console-and-file configuration is used. An env var
#: rather than a key in app.yaml because logging has to be configured before
#: that file is read — a failure loading it is the first thing worth logging.
LOGGER_PATH_ENV = "SIMPLE_ERP_LOGGER"
DEFAULT_LOGGER_PATH = "conf/logger.yaml"


def setup_logging(config_path: Optional[str] = None) -> None:
    """Configure logging from a YAML file.

    Args:
        config_path (Optional[str]): Path to the logging configuration.
            Defaults to what ``SIMPLE_ERP_LOGGER`` names, and to the
            development configuration when that is unset.

    Notes:
        A missing or unreadable file falls back to a basic configuration rather
        than aborting start-up: losing structured logs is bad, refusing to
        serve because of it is worse.
    """
    chosen = (
        config_path
        if config_path
        else os.environ.get(LOGGER_PATH_ENV, DEFAULT_LOGGER_PATH)
    )
    resolved = Path(chosen)
    if not resolved.exists():
        # main.py -> api -> src -> api -> backend
        resolved = Path(__file__).resolve().parents[3] / chosen
    try:
        with open(resolved, "r", encoding="utf-8") as config_file:
            configuration = yaml.safe_load(config_file)
        os.makedirs("logs", exist_ok=True)
        dictConfig(configuration)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).error(
            "Falling back to basic logging; could not read %s: %s.",
            resolved,
            exc,  # noqa: E501
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging on start-up and release the pool on shutdown.

    Args:
        app (FastAPI): The application being started.

    Yields:
        None: While the application serves traffic.

    Notes:
        - The database is deliberately **not** connected here. The connection
          manager connects lazily on first use, so the API still boots — and
          answers ``/health`` — when the database is not up yet. That is what
          lets it start alongside its database rather than strictly after it.
        - The photograph bucket **is** created here, and the failure to do so is
          survivable. A missing bucket makes every upload fail with a 503 that
          says nothing useful, and on a fresh object store there is nothing else
          that would ever create it. Creating it is idempotent, so a restart
          against an existing bucket is a no-op.
        - The notification relay is started here for the same reason the pool is
          not: it must outlive every request, and no request can own it. It is
          survivable too — an API with no broker still lists notifications, it
          just cannot announce them the moment they are written.
    """
    setup_logging()
    started_logger = logging.getLogger(__name__)
    started_logger.info("Application starting up.")
    geocoding = config.geocoding
    PostalAddress.apply_geocoding_settings(
        base_url=geocoding.base_url,
        user_agent=geocoding.user_agent,
        timeout_seconds=geocoding.timeout_seconds,
        country_codes=tuple(geocoding.country_codes),
    )
    started_logger.info("Geocoding configured against %s.", geocoding.base_url)
    try:
        if await get_object_storage().ensure_bucket():
            started_logger.info("Photograph bucket %s is ready.", config.s3.bucket)
        else:
            started_logger.warning(
                "Photograph bucket %s could not be prepared; uploads will fail "
                "until it exists.",
                config.s3.bucket,
            )
    except Exception as exc:  # noqa: BLE001 - the API must still start
        # The object store being unreachable is not a reason to refuse traffic:
        # everything that is not a photograph still works.
        started_logger.error("Could not prepare the photograph bucket: %s.", exc)  # noqa: E501
    await start_notification_relay()
    yield
    logging.getLogger(__name__).info("Application shutting down.")
    await stop_notification_relay()
    await close_connection_manager()


config = get_app_config()

app = FastAPI(
    title=config.server.title,
    version=config.server.version,
    description=(
        "Quoting and intervention planning for a home-care agency: customers, "
        "assistants, intervention types, quotes and the planning computation."
    ),
    docs_url="/docs",
    lifespan=lifespan,
)
app.add_middleware(TransactionMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
ExceptionHandlers(logger=logger).register(app)

app.include_router(observability_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(accounts_router)
app.include_router(companies_router)
app.include_router(hca_applications_router)
app.include_router(customers_router)
app.include_router(hca_photos_router)
app.include_router(hcas_router)
app.include_router(availability_router)
app.include_router(hca_skills_router)
app.include_router(intervention_types_router)
app.include_router(certifications_router)
app.include_router(skills_router)
app.include_router(quotes_router)
app.include_router(notifications_router)
app.include_router(me_router)
app.include_router(planning_runs_router)
app.include_router(planning_settings_router)
app.include_router(plannings_router)
app.include_router(interventions_router)
# The run router is mounted **before** the bill router, and the order is
# load-bearing: `/api/v1/bills/runs` and `/api/v1/bills/{bill_id}` match the
# same shape, so whichever is registered first wins. Reversed, asking for
# the run list would look up a bill numbered "runs" and answer 404.
app.include_router(billing_runs_router)
app.include_router(bills_router)
app.include_router(billing_settings_router)
app.include_router(webhooks_router)


def main() -> None:
    """Run the API with uvicorn.

    Notes:
        Reads the bind address from the same configuration the application
        uses, so the container and the process agree on the port.
    """
    setup_logging()
    uvicorn.run(
        "api.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
