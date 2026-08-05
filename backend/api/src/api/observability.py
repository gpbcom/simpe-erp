from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Response, status

# First-party imports
from api.dependencies import get_connection_manager
from models.enums import DatabaseStatus, ProbeStatus
from models.schemas.responses.health_response import HealthResponse
from models.schemas.responses.readiness_response import ReadinessResponse
from storage.db.connection_manager import DatabaseConnectionManager

logger: Logger = getLogger(__name__)

router = APIRouter(tags=["Observability"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the process is running.

    Returns:
        HealthResponse: Always ``ok``.

    Notes:
        Deliberately checks nothing. A liveness probe answers "should this
        container be restarted"; making it depend on the database would restart
        a perfectly healthy API every time the database blinked.
    """
    return HealthResponse(status=ProbeStatus.OK)


@router.get("/ready", response_model=ReadinessResponse)
async def ready(response: Response) -> ReadinessResponse:
    """Report whether the service can serve traffic.

    Args:
        response (Response): The outgoing response, whose status is set to 503
            when the database does not answer.

    Returns:
        ReadinessResponse: The readiness status and the database's state.

    Notes:
        Reports rather than raises, so the probe reads a body either way.
        Unlike ``/health`` this *does* touch the database: an API that cannot
        reach its store should be taken out of the load balancer, but not
        restarted.
    """
    try:
        manager: DatabaseConnectionManager = await get_connection_manager()
        reachable = await manager.ping()
    except Exception as exc:  # noqa: BLE001 - reported as not ready
        logger.error("Readiness check failed to reach the database: %s.", exc)
        reachable = False
    if not reachable:
        logger.warning("Service is not ready: the database did not answer.")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status=ProbeStatus.UNAVAILABLE, database=DatabaseStatus.UNREACHABLE
        )
    logger.debug("Readiness check passed.")
    return ReadinessResponse(status=ProbeStatus.OK, database=DatabaseStatus.REACHABLE)  # noqa: E501
