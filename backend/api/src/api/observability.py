from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends, Response, status

# First-party imports
from api.dependencies import get_connection_manager, get_metrics
from models.enums import DatabaseStatus, ProbeStatus
from models.schemas.responses.observability.health_response import HealthResponse
from models.schemas.responses.observability.readiness_response import ReadinessResponse
from service.observability.metrics import ApplicationMetrics
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


@router.get("/metrics", include_in_schema=False)
async def metrics(
    registry: ApplicationMetrics = Depends(get_metrics),
) -> Response:
    """Serve this instance's figures in the exposition format.

    Args:
        registry (ApplicationMetrics): This process's metrics registry.

    Returns:
        Response: The exposition body, with the content type Prometheus
        negotiates on.

    Notes:
        - **Unauthenticated**, like ``/health`` and ``/ready``, because a
          scraper has no account to sign in with. What it exposes is counts and
          durations — no identifier of a person, a customer or an agency
          appears in any label, which is a property
          :class:`~service.observability.metrics.ApplicationMetrics` is
          responsible for and has a test for. It should still be reachable only
          from inside the cluster. The ingress does not route it.
        - **Absent from the OpenAPI document.** It is not part of the API a
          client programs against, and including it would put a
          non-JSON endpoint in a schema every client generator reads.
        - Served per instance rather than aggregated. Each API replica holds
          its own readers and its own counts, and Prometheus is what adds them
          up — an application that aggregated first would be reporting a figure
          no single process could be asked about.
    """
    body, content_type = registry.render()
    return Response(content=body, media_type=content_type)
