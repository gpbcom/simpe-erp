from __future__ import annotations

# Standard library imports
from contextlib import asynccontextmanager
import logging
from logging.config import dictConfig
import os
from pathlib import Path
from typing import AsyncIterator

# Third-party imports
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import yaml

# First-party imports
from api.dependencies import (
    close_connection_manager,
    get_app_config,
    get_photo_storage,
)
from api.exception_handlers import ExceptionHandlers
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.transaction_middleware import TransactionMiddleware
from api.observability import router as observability_router
from api.v1.auth.accounts import router as accounts_router
from api.v1.auth.auth import router as auth_router
from api.v1.companies.companies import router as companies_router
from api.v1.customers.customers import router as customers_router
from api.v1.hcas.applications import router as hca_applications_router
from api.v1.hcas.availability import router as availability_router
from api.v1.hcas.hcas import router as hcas_router
from api.v1.hcas.photos import router as hca_photos_router
from api.v1.intervention_types.intervention_types import (
    router as intervention_types_router,
)
from api.v1.notifications.notifications import router as notifications_router
from api.v1.planning.plannings import router as plannings_router
from api.v1.planning.runs import router as planning_runs_router
from api.v1.planning.settings import router as planning_settings_router
from api.v1.quotes.quotes import router as quotes_router
from api.v1.users.users import router as users_router
from api.v1.webhooks.webhooks import router as webhooks_router
from models.geo.postal_address import PostalAddress

logger = logging.getLogger(__name__)


def setup_logging(config_path: str = "conf/logger.yaml") -> None:
    """Configure logging from a YAML file.

    Args:
        config_path (str): Path to the logging configuration.

    Notes:
        A missing or unreadable file falls back to a basic configuration rather
        than aborting start-up: losing structured logs is bad, refusing to
        serve because of it is worse.
    """
    resolved = Path(config_path)
    if not resolved.exists():
        # main.py -> api -> src -> api -> backend
        resolved = Path(__file__).resolve().parents[3] / config_path
    try:
        with open(resolved, "r", encoding="utf-8") as config_file:
            configuration = yaml.safe_load(config_file)
        os.makedirs("logs", exist_ok=True)
        dictConfig(configuration)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).error(
            "Falling back to basic logging; could not read %s: %s.", resolved, exc
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
        if await get_photo_storage().ensure_bucket():
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
        started_logger.error("Could not prepare the photograph bucket: %s.", exc)
    yield
    logging.getLogger(__name__).info("Application shutting down.")
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

# Added outermost-last: CORS must wrap the authentication middleware so a
# rejected credential still carries the CORS headers, or the browser reports an
# opaque network error instead of the 401.
# Added first, so it sits innermost: it must see the response the router
# produced, with the request's session still open.
app.add_middleware(TransactionMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Every domain exception is translated to its HTTP answer here rather than in
# the endpoints. See :class:`~api.exception_handlers.ExceptionHandlers`.
ExceptionHandlers(logger=logger).register(app)


app.include_router(observability_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(accounts_router)
app.include_router(companies_router)
app.include_router(hca_applications_router)
app.include_router(customers_router)
# The photograph router is included **before** the assistant router, and the
# order is load-bearing: both are mounted under /api/v1/hcas, and the assistant
# router's ``GET /{hca_id}`` would otherwise swallow the literal
# ``GET /photo-constraints`` — answering "no assistant 'photo-constraints'
# exists" for a route that has nothing to do with an assistant.
app.include_router(hca_photos_router)
app.include_router(hcas_router)
app.include_router(availability_router)
app.include_router(intervention_types_router)
app.include_router(quotes_router)
app.include_router(notifications_router)
app.include_router(planning_runs_router)
app.include_router(planning_settings_router)
app.include_router(plannings_router)
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
