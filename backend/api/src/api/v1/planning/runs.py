from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
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
    agency_id: Optional[str] = Query(default=None),
    service: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> List[PlanningRun]:
    """Start a planning computation for one team, one site, or the company.

    Args:
        period_start (date): First day to plan, inclusive.
        period_end (date): Last day to plan, inclusive.
        team_id (Optional[str]): The team to plan.
        agency_id (Optional[str]): The site to plan, every team of it that the
            caller runs. Read only when no team is named.
        service (PlanningService): The planning service.
        publisher (EventPublisher): Queues the solves for a worker.
        caller (User): The authenticated caller; enforces manager access, and
            decides which teams may be named.

    Returns:
        List[PlanningRun]: One pending run per team, each with an identifier to
        poll. Empty when the scope holds no team.

    Raises:
        MTPlanningPeriodTooLong: When the period runs backwards. Answered as a
            422 by the central handler.
        MTPlanningTeamForbidden: When the named team is not one the caller
            runs. Answered as a 403.
        MTPlanningScopeForbidden: When a manager names no scope at all, which
            is a request to rebuild the whole company. Answered as a 403.

    Notes:
        - **Manager, not administrator, and that is the point of the change.** A
          run used to rewrite every assistant's calendar in the agency, which is
          why only an administrator could ask for one. It now rewrites one
          team's, which is exactly the thing a manager is responsible for. The
          *row-level* check — that this particular team is theirs — is in the
          service, because a route guard can only prove a rank.
        - **Three scopes, narrowest first: a team, a site, the company.** A team
          is named by ``team_id`` and a site by ``agency_id``. Naming neither is
          the whole company, and that is an administrator's act because it
          rewrites the calendar of every assistant the company employs. A
          manager who names neither is refused rather than quietly given their
          own teams — being told the company was re-planned when one team was
          would be worse than the refusal.
        - **A list, not a run.** A site holds several teams and a company holds
          several sites, so every scope but the narrowest fans out. Returning
          one run would have meant either silently planning only the first team
          or inventing a company-wide run that the delete would then have to be
          scoped by all over again.
        - ``team_id`` wins when both are given, rather than being refused as
          ambiguous: it is the narrower of the two, so honouring it can only
          plan less than the caller asked for, and a client that sends both has
          a stale field rather than a conflicting intention.
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
    teams = await service.teams_to_plan(caller, team_id, agency_id)
    if not teams:
        logger.warning(
            "%s asked for a planning of team=%s site=%s, which holds no team "
            "they run. Nothing was queued.",
            caller.email,
            team_id,
            agency_id,
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
    caller: User = Depends(get_manager_user),
) -> List[PlanningRun]:
    """List the planning runs of the teams the caller may read.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        service (PlanningService): The planning service.
        caller (User): The authenticated caller; enforces manager access, and
            decides which runs are listed.

    Returns:
        List[PlanningRun]: The runs, most recent period first.

    Notes:
        **Manager, not administrator, and without this a manager's button does
        nothing they can see.** This is what the screen polls while a
        computation is in flight: it is where "computing…" comes from, and
        where the result and its unplaced visits are read. Left at
        administrator, a manager could start a run and then watch a page that
        never changed — which is indistinguishable from a planning that was
        never computed.
    """
    return await service.list_runs(caller, page=page, size=size)


@router.get("/runs/{run_id}", response_model=PlanningRun)
async def get_planning_run(
    run_id: str,
    service: PlanningService = Depends(get_planning_service),
    caller: User = Depends(get_manager_user),
) -> PlanningRun:
    """Report a planning run's progress or result.

    Args:
        run_id (str): The run to read.
        service (PlanningService): The planning service.
        caller (User): The authenticated caller; enforces manager access, and
            decides whether this run is theirs to read.

    Returns:
        PlanningRun: The run.

    Raises:
        MTPlanningRunNotFound: If no such run exists. Answered as a 404.
        MTPlanningForbidden: If it rebuilt a team the caller may not read;
            answered as a 403.

    Notes:
        - This is the polling endpoint. A succeeded run may still carry
          ``unassigned_requirement_ids`` — the plan is real, and that list is
          what would not fit.
        - The row-level check is in the service rather than the guard. Every
          manager holds real run identifiers, because starting a run hands them
          one; without the check they could poll a colleague's and learn how
          much of that team's week would not fit.
    """
    return await service.run(run_id, caller)
