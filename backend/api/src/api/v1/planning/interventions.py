from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_event_publisher,
    get_intervention_service,
    get_manager_user,
    get_planning_service,
)
from models.auth.user import User
from models.enums import EventRoutingKey
from models.planning.planning_run import PlanningRun
from models.quoting.quote import Quote
from models.schemas.requests.intervention_type_change_request import (
    InterventionTypeChangeRequest,
)
from service.messaging.publisher import EventPublisher
from service.planning.exceptions import MTPlanningPeriodTooLong
from service.planning.interventions import InterventionService
from service.planning.plannings import PlanningService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/planning/interventions", tags=["Interventions"])


@router.delete(
    "/{intervention_id}",
    response_model=PlanningRun,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_intervention(
    intervention_id: str,
    period_start: date = Query(...),
    period_end: date = Query(...),
    interventions: InterventionService = Depends(get_intervention_service),
    plannings: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> PlanningRun:
    """Cancel a visit, bill for it no longer, and replan the period.

    Args:
        intervention_id (str): The visit to cancel.
        period_start (date): First day to replan, inclusive.
        period_end (date): Last day to replan, inclusive.
        interventions (InterventionService): Edits the visit and its line.
        plannings (PlanningService): Records the replan.
        publisher (EventPublisher): Queues the solve for a worker.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        PlanningRun: The pending replan, with the identifier to poll.

    Raises:
        MTInterventionNotFound: If no such visit exists; answered as a 404.
        MTInterventionNotQuoted: If its quote line has vanished; answered as a
            409.
        MTPlanningPeriodTooLong: If the period runs backwards; answered as a
            422.

    Notes:
        - Answers **202**, like every other request that ends in a solve. The
          quote is already changed by the time this returns; the calendar
          catches up when the worker finishes.
        - **The period is the window the caller is looking at**, not one
          derived here. A cancellation is an edit to a screen showing six
          weeks, and replanning a different span than the one on screen would
          leave a manager comparing two answers.
        - Cancelling is **manager work, not administrator work**, unlike asking
          for a planning from scratch. One visit is a thing a manager knows
          about — the customer rang and cancelled — while a full recompute
          rewrites every assistant's calendar on purpose. The replan that
          follows is a consequence of the edit, not a second decision, so it is
          not gated again.
    """
    if period_end < period_start:
        logger.warning(
            "Refusing to replan after a cancellation: %s precedes %s.",
            period_end,
            period_start,
        )
        raise MTPlanningPeriodTooLong(
            f"Invalid period: {period_end} precedes {period_start}."
        )
    quote = await interventions.delete(intervention_id)
    logger.info(
        "%s cancelled intervention %s; quote %s.",
        caller.email,
        intervention_id,
        quote.reference if quote else "deleted with its last line",
    )
    run = await plannings.request_run(
        requested_by=caller.id or caller.email,
        period_start=period_start,
        period_end=period_end,
    )
    queued = await publisher.publish(
        EventRoutingKey.PLANNING_RUN_REQUESTED,
        caller.company_id,
        {"run_id": run.id, "company_id": caller.company_id},
    )
    if not queued:
        logger.error(
            "Replan %s after cancelling intervention %s is recorded but could "
            "not be queued; it stays pending until the broker is reachable.",
            run.id,
            intervention_id,
        )
    return run


@router.patch("/{intervention_id}/type", response_model=Quote)
async def change_intervention_type(
    intervention_id: str,
    payload: InterventionTypeChangeRequest,
    service: InterventionService = Depends(get_intervention_service),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Sell a visit as a different service, and reprice its quote.

    Args:
        intervention_id (str): The visit to re-classify.
        payload (InterventionTypeChangeRequest): The catalogue entry to sell
            it as.
        service (InterventionService): Edits the visit and its line.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The repriced quote, so the caller sees the new totals without a
        second request.

    Raises:
        MTInterventionNotFound: If no such visit exists; answered as a 404.
        MTInterventionNotQuoted: If its quote line has vanished; answered as a
            409.
        MTInterventionTypeNotFound: If the catalogue has no such entry;
            answered as a 404.

    Notes:
        No replan follows. The service changes what the hour is *called* and
        what it costs, not when it happens or how long it takes — the line
        keeps its day, its window and its duration, so every constraint the
        solver placed the visit under still holds. Replanning anyway would
        reshuffle a dozen calendars to arrive at the same answer.
    """
    quote = await service.change_type(intervention_id, payload.intervention_type_id)
    logger.info(
        "%s re-classified intervention %s; quote %s now totals %s TTC.",
        caller.email,
        intervention_id,
        quote.reference,
        quote.total_ttc,
    )
    return quote
