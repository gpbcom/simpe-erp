from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.exc import SQLAlchemyError

# First-party imports
from api.dependencies import (
    get_customer_portal_service,
    get_customer_user,
    get_event_publisher,
    get_planning_service,
)
from models.auth.user import User
from models.billing.bill import Bill
from models.people.customer import Customer
from models.planning.intervention.intervention import Intervention
from models.quoting.quote import Quote
from models.schemas.requests.customers.customer_profile_update_request import (
    CustomerProfileUpdateRequest,
)
from models.schemas.requests.customers.intervention_reschedule_request import (
    InterventionRescheduleRequest,
)
from service.customers.portal import CustomerPortalService
from service.messaging.publisher import EventPublisher
from service.planning.plannings import PlanningService

logger: Logger = getLogger(__name__)

# A namespace of its own rather than `/api/v1/me`, and the reason is one
# character: `/me/customers` already means *the assistant's portfolio*, so a
# household's own record under `/me` would be `/me/customer` — a different
# guard, an opposite meaning, and a typo away from each other. A separate
# prefix also lets every route here carry the same guard by construction.
router = APIRouter(prefix="/api/v1/portal", tags=["Customer portal"])


async def _queue_replan(
    plannings: PlanningService,
    publisher: EventPublisher,
    caller: User,
    period: Optional[Tuple[date, date]],
    reason: str,
) -> None:
    """Queue a solve after a household changed their own work.

    Args:
        plannings (PlanningService): Records and publishes the run.
        publisher (EventPublisher): Queues the solve for a worker.
        caller (User): The household who made the change.
        period (Optional[Tuple[date, date]]): The days to replan, measured
            **before** the change, or ``None`` when they had no future visit.
        reason (str): What made the replan necessary, for the log.

    Notes:
        - **The reason this is not optional.** A cancelled or moved visit is
          still sitting on an assistant's calendar until a run recomputes the
          period. Left there, somebody is sent to a door for work the household
          has withdrawn — which is the single worst thing the portal could
          cause, and it looks like nothing went wrong until it happens.
        - Failures here do not fail the request. By the time this runs the
          household's change is stored and correct; raising would report a
          failure for an operation that succeeded. The cost is a schedule that
          stays stale until the next run, which is a WARNING somebody can act
          on rather than an error the household cannot.
        - Nothing is returned. A household is not polling a planning run — they
          are told their change is with the agency.
    """
    if period is None:
        logger.info(
            "Household %s had no future visit. No replan is queued.",
            caller.customer_id,
        )
        return
    logger.info(
        "Queueing a replan of %s to %s because household %s %s.",
        period[0],
        period[1],
        caller.customer_id,
        reason,
    )
    try:
        team_ids = await plannings.future_teams_for_customer(str(caller.customer_id))
        runs = await plannings.queue_replan(
            requested_by=caller.id or caller.email,
            company_id=caller.company_id,
            team_ids=team_ids,
            period=period,
            publisher=publisher,
            reason=f"household {caller.customer_id} {reason}",
        )
    except Exception:  # noqa: BLE001 - reported, never fatal to the household
        logger.error(
            "Could not queue a replan after household %s %s. Their calendar "
            "still shows the old arrangement until a run is started by hand.",
            caller.customer_id,
            reason,
        )
        return
    logger.debug("Queued %d replan(s).", len(runs))


@router.get("/profile", response_model=Customer)
async def read_profile(
    service: CustomerPortalService = Depends(get_customer_portal_service),
    caller: User = Depends(get_customer_user),
) -> Customer:
    """Return the household's own record.

    Args:
        service (CustomerPortalService): The portal service.
        caller (User): The authenticated household.

    Returns:
        Customer: Their record.

    Raises:
        MTCustomerNotFound: If the linked record no longer exists. A 404.

    Notes:
        **The household comes from the credential**, never from a path or a
        query parameter — so there is no identifier a customer could point at
        somebody else's file. Every route in this module works the same way.
    """
    logger.debug("Household %s is reading their profile.", caller.customer_id)
    return await service.profile(str(caller.customer_id))


@router.put("/profile", response_model=Customer)
async def update_profile(
    payload: CustomerProfileUpdateRequest,
    service: CustomerPortalService = Depends(get_customer_portal_service),
    caller: User = Depends(get_customer_user),
) -> Customer:
    """Correct the household's own contact details.

    Args:
        payload (CustomerProfileUpdateRequest): The new contact block.
        service (CustomerPortalService): The portal service.
        caller (User): The authenticated household.

    Returns:
        Customer: The updated record.

    Raises:
        MTCustomerNotFound: If the linked record no longer exists. A 404.
        MTInvalidCustomerProfileUpdateRequestException: If a name is empty. A
            422.

    Notes:
        The payload carries the contact block and **nothing else**. It has no
        field for the registration status — a household that could set their own
        would promote themselves into the planning — and none for the billing
        periodicity, which is a term the agency agrees.
    """
    logger.info("Household %s is correcting their details.", caller.customer_id)
    return await service.update_profile(str(caller.customer_id), payload)


@router.get("/planning", response_model=List[Intervention])
async def read_planning(
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: CustomerPortalService = Depends(get_customer_portal_service),
    caller: User = Depends(get_customer_user),
) -> List[Intervention]:
    """Return the household's visits over a period.

    Args:
        period_start (date): First day of interest, inclusive.
        period_end (date): Last day of interest, inclusive.
        service (CustomerPortalService): The portal service.
        caller (User): The authenticated household.

    Returns:
        List[Intervention]: Their visits, in day and time order.

    Notes:
        A period is required rather than defaulted. The calendar always knows
        which weeks it is showing, and an unbounded read would return every
        visit the household has ever had in order to draw seven days.
    """
    logger.debug(
        "Household %s is reading %s to %s.",
        caller.customer_id,
        period_start,
        period_end,
    )
    if (period_end - period_start).days > 366:
        logger.warning(
            "Household %s asked for %d days at once.",
            caller.customer_id,
            (period_end - period_start).days,
        )
    try:
        return await service.planning(str(caller.customer_id), period_start, period_end)
    except SQLAlchemyError:
        logger.error("Reading the planning of %s failed.", caller.customer_id)
        raise


@router.get("/quotes", response_model=List[Quote])
async def read_quotes(
    service: CustomerPortalService = Depends(get_customer_portal_service),
    caller: User = Depends(get_customer_user),
) -> List[Quote]:
    """Return every quote written for the household.

    Args:
        service (CustomerPortalService): The portal service.
        caller (User): The authenticated household.

    Returns:
        List[Quote]: Their quotes, newest first.

    Raises:
        MTCustomerNotFound: If the linked record no longer exists. A 404.

    Notes:
        Unfiltered, including refused and expired ones. A household asking "what
        did you quote me in March" is asking about the history, and a list
        narrowed to what is live answers a different question without saying so.
    """
    logger.debug("Household %s is reading their quotes.", caller.customer_id)
    return await service.quotes(str(caller.customer_id))


@router.post("/interventions/{intervention_id}/cancel", response_model=Quote)
async def cancel_visit(
    intervention_id: str,
    service: CustomerPortalService = Depends(get_customer_portal_service),
    plannings: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_customer_user),
) -> Quote:
    """Cancel one visit, and send its quote back for validation.

    Args:
        intervention_id (str): The visit to cancel.
        service (CustomerPortalService): The portal service.
        plannings (PlanningService): Measures the period to replan.
        publisher (EventPublisher): Queues the solve for a worker.
        caller (User): The authenticated household.

    Returns:
        Quote: The repriced quote, awaiting validation.

    Raises:
        MTCustomerNotFound: If the visit does not exist, or belongs to another
            household. A **404 in both cases**, deliberately.

    Notes:
        - **The quote goes back to `pending-validation`.** The household has
          changed what the agency agreed to deliver, so the agreement is no
          longer current. Until a manager re-validates it, nothing on that quote
          is scheduled — which the screen says rather than showing an empty
          calendar.
        - Cancelling removes the *line*, not only the visit: the next run
          rebuilds the period from the quote, so a visit removed on its own
          would reappear within the hour.
        - **A replan is queued**, and it is the most important thing this route
          does. The household's remaining work is unaffected, but every
          assistant who was due to visit them now has a gap — and, far worse,
          any visit left on a calendar for work nobody agreed to is an assistant
          turning up at somebody's door. The period is measured **before** the
          cancellation, because afterwards the visit is gone and there is
          nothing left to measure.
        - The run identifier is not returned. A household is not polling a
          planning run. They are told their change is with the agency.
    """
    logger.info(
        "Household %s is cancelling visit %s.", caller.customer_id, intervention_id
    )
    period = await plannings.future_period_for_customer(str(caller.customer_id))
    try:
        quote = await service.cancel_visit(str(caller.customer_id), intervention_id)
    except SQLAlchemyError:
        logger.error("Cancelling visit %s failed.", intervention_id)
        raise
    await _queue_replan(plannings, publisher, caller, period, "cancelled a visit")
    return quote


@router.post("/interventions/{intervention_id}/reschedule", response_model=Quote)
async def reschedule_visit(
    intervention_id: str,
    payload: InterventionRescheduleRequest,
    service: CustomerPortalService = Depends(get_customer_portal_service),
    plannings: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_customer_user),
) -> Quote:
    """Move one visit, and send its quote back for validation.

    Args:
        intervention_id (str): The visit to move.
        payload (InterventionRescheduleRequest): The day and the window.
        service (CustomerPortalService): The portal service.
        plannings (PlanningService): Measures the period to replan.
        publisher (EventPublisher): Queues the solve for a worker.
        caller (User): The authenticated household.

    Returns:
        Quote: The repriced quote, awaiting validation.

    Raises:
        MTCustomerNotFound: If the visit does not exist, or is not theirs; 404.
        MTInvalidInterventionRescheduleRequestException: If the window is
            empty or outside the day. A 422.
        MTQuoteLineWindowTooShort: If the window is narrower than the work
            takes. A 422.

    Notes:
        - **A window, not a time.** The household says when they are available;
          the solver picks the moment inside it, against the assistant's round.
        - **It reprices**: a visit moved onto a Sunday or a holiday costs more,
          because the surcharge is a property of the day. So the household
          cannot move work without the agency seeing the new price — a second
          reason the quote returns to the validation queue.
        - **A replan is queued.** Until one runs, the stored visit still names
          the old day, so an assistant's calendar would send them to the door at
          a time the household has already said does not suit.
    """
    logger.info(
        "Household %s is moving visit %s to %s.",
        caller.customer_id,
        intervention_id,
        payload.day,
    )
    period = await plannings.future_period_for_customer(str(caller.customer_id))
    try:
        quote = await service.reschedule_visit(
            customer_id=str(caller.customer_id),
            intervention_id=intervention_id,
            day=payload.day,
            start_minute=payload.start_minute,
            end_minute=payload.end_minute,
        )
    except SQLAlchemyError:
        logger.error("Moving visit %s failed.", intervention_id)
        raise
    await _queue_replan(plannings, publisher, caller, period, "moved a visit")
    return quote


@router.get(
    "/quotes/{quote_id}/document",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_quote(
    quote_id: str,
    service: CustomerPortalService = Depends(get_customer_portal_service),
    caller: User = Depends(get_customer_user),
) -> Response:
    """Serve one of the household's quotes as a PDF.

    Args:
        quote_id (str): The quote to render.
        service (CustomerPortalService): The portal service.
        caller (User): The authenticated household.

    Returns:
        Response: The document, as ``application/pdf``.

    Raises:
        MTCustomerNotFound: If the quote is not theirs, or does not exist —
            **the same 404 for both**, so nobody can walk the identifier space.
        MTQuoteNotPriced: If it has never been priced. A 422.

    Notes:
        Written in the **household's** language. The same offer downloaded by a
        manager comes out in theirs. It is one document with two readers.
    """
    logger.info("Household %s is downloading quote %s.", caller.customer_id, quote_id)
    payload, filename = await service.quote_document(
        str(caller.customer_id), quote_id, caller.language
    )
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bills", response_model=List[Bill])
async def read_bills(
    service: CustomerPortalService = Depends(get_customer_portal_service),
    caller: User = Depends(get_customer_user),
) -> List[Bill]:
    """Return every invoice issued to the household.

    Args:
        service (CustomerPortalService): The portal service.
        caller (User): The authenticated household.

    Returns:
        List[Bill]: Their invoices, most recent period first.

    Notes:
        Narrowed **in the query** to this household. A page of the agency's
        invoices filtered afterwards has already read what other families pay
        for their care.
    """
    logger.debug("Household %s is reading their invoices.", caller.customer_id)
    return await service.bills(str(caller.customer_id), caller.company_id)


@router.get(
    "/bills/{bill_id}/document",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_bill(
    bill_id: str,
    service: CustomerPortalService = Depends(get_customer_portal_service),
    caller: User = Depends(get_customer_user),
) -> Response:
    """Serve one of the household's invoices as a PDF.

    Args:
        bill_id (str): The invoice to serve.
        service (CustomerPortalService): The portal service.
        caller (User): The authenticated household.

    Returns:
        Response: The document, as ``application/pdf``.

    Raises:
        MTCustomerNotFound: If the invoice is not theirs, or does not exist;
            a 404 in both cases.

    Notes:
        **Streamed through this endpoint rather than served from the bucket**,
        exactly as the manager's download is. The objects sit under a private
        prefix precisely so the bearer guard is the only way to them. A
        presigned URL would put a household's invoice outside it.
    """
    logger.info("Household %s is downloading invoice %s.", caller.customer_id, bill_id)
    payload, filename = await service.bill_document(str(caller.customer_id), bill_id)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
