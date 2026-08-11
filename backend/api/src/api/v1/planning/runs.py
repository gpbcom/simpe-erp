from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_event_publisher,
    get_planning_service,
)
from models.auth.user import User
from models.enums import EventRoutingKey
from models.planning.planning_run import PlanningRun
from service.messaging.publisher import EventPublisher
from service.planning.exceptions import (
    MTPlanningPeriodTooLong,
)
from service.planning.plannings import PlanningService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/planning", tags=["Planning runs"])


@router.post("/runs", response_model=PlanningRun, status_code=status.HTTP_202_ACCEPTED)
async def start_planning_run(
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_admin_user),
) -> PlanningRun:
    """Start a planning computation over a period.

    Args:
        period_start (date): First day to plan, inclusive.
        period_end (date): Last day to plan, inclusive.
        service (PlanningService): The planning service.
        publisher (EventPublisher): Queues the solve for a worker.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        PlanningRun: The pending run, with the identifier to poll.

    Raises:
        MTPlanningPeriodTooLong: When the period runs backwards; answered as a
            422 by the central handler.

    Notes:
        - Answers **202**, not 200. The solve is CPU-bound and runs for the
          configured budget in a separate worker process, so holding the request
          open for it would tie up a connection and time out the client. Poll
          ``GET /runs/{id}`` until the status is terminal.
        - The run is **recorded before it is queued**, and the record is what the
          caller is given. If the broker is unreachable the run stays ``pending``
          rather than vanishing: the identifier the caller polls is real either
          way, and the work can be re-queued without anybody having to reconstruct
          what was asked for. That is the whole reason this moved off a FastAPI
          background task — one lost the run entirely on a restart.
        - Running the computation is administrator-only: it rewrites every
          assistant's calendar for the period.
    """
    if period_end < period_start:
        logger.warning(
            "Refusing a planning run whose period runs backwards: %s to %s.",
            period_start,
            period_end,
        )
        raise MTPlanningPeriodTooLong(
            f"Invalid period: {period_end} precedes {period_start}."
        )
    run = await service.request_run(
        requested_by=caller.id or caller.email,
        company_id=caller.company_id,
        period_start=period_start,
        period_end=period_end,
    )
    logger.info(
        "Scheduling planning run %s for %s to %s.",
        run.id,
        period_start,
        period_end,
    )
    queued = await publisher.publish(
        EventRoutingKey.PLANNING_RUN_REQUESTED,
        caller.company_id,
        # Carried in the payload as well as the routing key: the worker
        # echoes it back when announcing the run finished, rather than
        # deriving the agency a second time and risking a different answer.
        {"run_id": run.id, "company_id": caller.company_id},
    )
    if not queued:
        logger.error(
            "Planning run %s is recorded but could not be queued; it stays "
            "pending until the broker is reachable.",
            run.id,
        )
    return run


@router.get("/runs", response_model=List[PlanningRun])
async def list_planning_runs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    service: PlanningService = Depends(get_planning_service),
    _: User = Depends(get_admin_user),
) -> List[PlanningRun]:
    """List the planning runs.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        service (PlanningService): The planning service.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        List[PlanningRun]: The runs, most recent period first.
    """
    return await service.list_runs(page=page, size=size)


@router.get("/runs/{run_id}", response_model=PlanningRun)
async def get_planning_run(
    run_id: str,
    service: PlanningService = Depends(get_planning_service),
    _: User = Depends(get_admin_user),
) -> PlanningRun:
    """Report a planning run's progress or result.

    Args:
        run_id (str): The run to read.
        service (PlanningService): The planning service.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        PlanningRun: The run.

    Raises:
        MTPlanningRunNotFound: If no such run exists; answered as a 404.

    Notes:
        This is the polling endpoint. A succeeded run may still carry
        ``unassigned_requirement_ids`` — the plan is real, and that list is
        what would not fit.
    """
    return await service.get_run(run_id)
