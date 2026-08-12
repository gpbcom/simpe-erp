from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_event_publisher,
    get_manager_user,
    get_planning_service,
)
from models.auth.user import User
from models.planning.planning_run import PlanningRun
from service.messaging.publisher import EventPublisher
from service.planning.exceptions import (
    MTPlanningPeriodTooLong,
)
from service.planning.plannings import PlanningService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/planning", tags=["Planning runs"])


@router.post(
    "/runs",
    response_model=List[PlanningRun],
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_planning_run(
    period_start: date = Query(...),
    period_end: date = Query(...),
    team_id: Optional[str] = Query(default=None),
    service: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> List[PlanningRun]:
    """Start a planning computation over a period, for one team or for all.

    Args:
        period_start (date): First day to plan, inclusive.
        period_end (date): Last day to plan, inclusive.
        team_id (Optional[str]): The team to plan. Omitted, every team the
            caller runs is planned.
        service (PlanningService): The planning service.
        publisher (EventPublisher): Queues the solves for a worker.
        caller (User): The authenticated caller; enforces manager access, and
            decides which teams may be named.

    Returns:
        List[PlanningRun]: One pending run per team, each with an identifier to
        poll. Empty when the caller runs no team.

    Raises:
        MTPlanningPeriodTooLong: When the period runs backwards; answered as a
            422 by the central handler.
        MTPlanningTeamForbidden: When the named team is not one the caller
            runs; answered as a 403.

    Notes:
        - **Manager, not administrator, and that is the point of the change.** A
          run used to rewrite every assistant's calendar in the agency, which is
          why only an administrator could ask for one. It now rewrites one
          team's, which is exactly the thing a manager is responsible for. The
          *row-level* check — that this particular team is theirs — is in the
          service, because a route guard can only prove a rank.
        - **A list, not a run.** Omitting the team means "every team I run", so
          an administrator's button is a fan-out over the company and a
          manager's is over theirs. Returning one run would have meant either
          silently planning only the first team or inventing a company-wide run
          that the delete would then have to be scoped by all over again.
        - Answers **202**, not 200. Each solve is CPU-bound and runs for the
          configured budget in a separate worker process, so holding the request
          open would tie up a connection and time out the client. Poll
          ``GET /runs/{id}`` for each until its status is terminal.
        - Each run is **recorded before it is queued**, and the records are what
          the caller is given. If the broker is unreachable a run stays
          ``pending`` rather than vanishing: the identifier is real either way,
          and the work can be re-queued without anybody reconstructing what was
          asked for. That is why this is not a background task — one lost the
          run entirely on a restart.
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
    teams = await service.teams_to_plan(caller, team_id)
    if not teams:
        logger.warning(
            "%s asked for a planning but runs no team; nothing was queued.",
            caller.email,
        )
    runs = await service.queue_replan(
        requested_by=caller.id or caller.email,
        company_id=caller.company_id,
        team_ids=teams,
        period=(period_start, period_end),
        publisher=publisher,
        reason="a planning was requested",
    )
    logger.info(
        "Scheduled %d planning run(s) for %s to %s.",
        len(runs),
        period_start,
        period_end,
    )
    return runs


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
