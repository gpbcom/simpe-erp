from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, Response, status

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_event_publisher,
    get_manager_user,
    get_quote_document_service,
    get_quote_service,
)
from models.auth.user import User
from models.enums import EventRoutingKey, QuoteStatus
from models.quoting.quote import Quote
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate
from models.schemas.requests.quoting.quote_create_request import (
    QuoteCreateRequest,
)
from models.schemas.requests.quoting.quote_filter import QuoteFilter
from models.schemas.requests.quoting.quote_header_request import (
    QuoteHeaderRequest,
)
from models.schemas.requests.quoting.quote_interruption_request import (
    QuoteInterruptionRequest,
)
from models.schemas.requests.quoting.quote_lines_request import QuoteLinesRequest
from models.schemas.requests.quoting.quote_reschedule_request import (
    QuoteRescheduleRequest,
)
from models.schemas.requests.quoting.quote_team_request import QuoteTeamRequest
from service.messaging.publisher import EventPublisher
from service.quotes.documents import QuoteDocumentService
from service.quotes.quotes import QuoteService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/quotes", tags=["Quotes"])


@router.post("", response_model=Quote, status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: QuoteCreateRequest,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Create a quote and price whatever lines it arrives with.

    Args:
        payload (QuoteCreateRequest): What the quote should offer.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the quote's author.

    Returns:
        Quote: The stored, priced quote with its weekly totals.

    Raises:
        MTQuoteUnassignable: If no team can be given the work — the household is
            unknown, or the company has no team with anybody on it; 422.
        MTPricingUnknownInterventionType: If a line names a type that is not in
            the catalog. Answered as a 422.

    Notes:
        - The author and the agency are taken from the credential, never from
          the payload. A manager's quote needs no validation step — they are the
          ones who would sign it off — so it lands as a draft ready to send.
        - **The payload goes to the service whole**, rather than being turned
          into a quote here. Which team delivers the work is decided from where
          the household lives and how much each team already carries, and that
          rule has to be in one place: the assistant's route at
          ``POST /api/v1/me/quotes`` calls the same method.
    """
    return await service.create(
        payload, caller.company_id, author_id=caller.id or caller.email
    )


@router.get("", response_model=List[Quote])
async def list_quotes(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    customer_id: Optional[str] = Query(default=None),
    quote_status: Optional[QuoteStatus] = Query(default=None, alias="status"),
    authored_by: Optional[str] = Query(default=None),
    quote_filter: QuoteFilter = Depends(),
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_manager_user),
) -> List[Quote]:
    """List the quotes the caller's teams hold, narrowed by any filters sent.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        customer_id (Optional[str]): Restrict to one customer.
        quote_status (Optional[QuoteStatus]): Restrict to one status.
        authored_by (Optional[str]): Restrict to one author's quotes.
        quote_filter (QuoteFilter): The filters, bound from the query string.
            Every field is optional and an absent one narrows nothing.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access, and
            decides which teams' quotes come back.

    Returns:
        List[Quote]: The matching quotes of the teams the caller may read.

    Raises:
        MTInvalidQuoteFilterException: If a filter is malformed. Answered as a
            422.

    Notes:
        - Filtering by ``status=pending-validation`` is what the manager's
          validation queue is: the quotes an assistant has submitted and nobody
          has ruled on yet.
        - The three older query parameters stay, and the filter carries the
          same names. They are passed on separately rather than merged here,
          because the store is where the rule about which one wins belongs —
          and for ``authored_by`` that rule is a permission, not a preference.
        - **A manager now sees their own teams' quotes rather than the whole
          agency's**, and an administrator still sees everything. The narrowing
          is the service's, applied in the statement; ``authored_by`` remains a
          *filter* on top of it, so a manager narrowing by an author outside
          their teams simply gets nothing rather than somebody else's book.
    """
    if authored_by is not None:
        logger.debug(
            "%s is also narrowing the quote list to author %s.",
            caller.email,
            authored_by,
        )
    return await service.list(
        caller,
        page=page,
        size=size,
        customer_id=customer_id,
        status=quote_status,
        quote_filter=quote_filter,
    )


@router.post("/renewals/run", response_model=List[Quote])
async def run_renewals(
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> List[Quote]:
    """Write successors for every arrangement that has expired.

    Args:
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[Quote]: The successors created, which is empty on most days.

    Notes:
        **Declared before ``/{quote_id}``**, or the path would be read as a
        request about the quote whose identifier is ``"renewals"``.

        **Safe to call repeatedly.** A quote that already has a successor is
        skipped, so a second run the same day creates nothing. That is what
        makes this callable from a timer, from the worker, or by hand when
        somebody notices the timer did not fire — without billing a customer
        twice for one period.
    """
    logger.info("Running the renewal sweep.")
    return await service.renew_due()


@router.post("/{quote_id}/reschedule", response_model=Quote)
async def reschedule_quote_line(
    quote_id: str,
    request: QuoteRescheduleRequest,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Move one line onto a time the planner offered, and reprice.

    Args:
        quote_id (str): The quote to change.
        request (QuoteRescheduleRequest): The line, the day and the window.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The repriced quote, still waiting to be validated.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteLineNotFound: If the quote no longer carries that line;
            answered as a 404.
        MTQuoteLineWindowTooShort: If the window is narrower than the work
            takes. Answered as a 422.
        MTPricingUnknownInterventionType: If the line names a type that is not
            in the catalogue. Answered as a 422.

    Notes:
        - **This is how the slots on the validation screen become clickable.**
          A planner that returned a quote also offers the times somebody
          qualified is free. Accepting one here writes the new day and window
          onto the line it belongs to.
        - **The status does not move.** Accepting a time answers *when* the
          work happens, not *whether* the agency has agreed to it — so the
          quote stays in the validation queue and a manager still has to
          validate it.
        - The offered slot names an assistant and this route ignores it. A
          quote records what is sold and when; who does it is the planner's to
          decide on the next run, and storing a preference the run need not
          honour would be a promise nothing keeps.
    """
    logger.info(
        "%s is moving line %s of quote %s to %s.",
        caller.email,
        request.quote_line_id,
        quote_id,
        request.day,
    )
    return await service.reschedule_line(
        quote_id=quote_id,
        quote_line_id=request.quote_line_id,
        day=request.day,
        start_minute=request.start_minute,
        end_minute=request.end_minute,
    )


@router.post("/{quote_id}/interrupt", response_model=Quote)
async def interrupt_quote(
    quote_id: str,
    request: QuoteInterruptionRequest,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Give a running arrangement a last day, and reprice it.

    Args:
        quote_id (str): The quote to end.
        request (QuoteInterruptionRequest): The final day it runs.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The shortened quote, with its new total.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteInvalidInterruption: If the day falls before the quote was
            issued or before its first service. Answered as a 422.

    Notes:
        The cancelled visits stay on the quote, priced, and stop counting
        towards the total — so the document can still answer why the invoice
        came in under what was signed. The planner stops producing work the day
        after ``last_day``.
    """
    logger.info("Interrupting quote %s on %s.", quote_id, request.last_day)
    return await service.interrupt(quote_id, request.last_day)


@router.patch("/{quote_id}/auto-renew", response_model=Quote)
async def set_quote_auto_renew(
    quote_id: str,
    enabled: bool = Query(...),
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Record whether a quote writes a successor when it expires.

    Args:
        quote_id (str): The quote to change.
        enabled (bool): Whether renewal is wanted.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The updated quote.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.

    Notes:
        Nothing is renewed until the quote reaches ``valid_until``, so turning
        this on and off before then costs nothing.
    """
    logger.info("Setting auto-renewal on quote %s to %s.", quote_id, enabled)
    return await service.set_auto_renew(quote_id, enabled)


@router.patch("/{quote_id}/team", response_model=Quote)
async def set_quote_team(
    quote_id: str,
    payload: QuoteTeamRequest,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Move a quote to a different team.

    Args:
        quote_id (str): The quote to move.
        payload (QuoteTeamRequest): The team that will deliver it instead.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access, and is
            checked against both the team the quote leaves and the one it joins.

    Returns:
        Quote: The updated quote.

    Raises:
        MTQuoteNotFound: If no such quote exists, or it belongs to another
            company. Answered as a 404.
        MTQuoteTeamForbidden: If the caller runs neither team; 403.
        MTTeamNotFound: If the destination team does not exist; 404.

    Notes:
        - Attribution happens once, when the quote is written. This exists for
          the two cases the rule cannot see: a proximity decision that was
          wrong, and a household that has moved. It is deliberately **manual** —
          re-attributing automatically would move work a manager has already
          validated, and with it visits somebody has been told about.
        - The **guard is manager, and the row check is in the service**, which
          is the codebase's standing division: a route can prove the caller's
          rank, but only the service can prove that both of these particular
          teams are theirs.
        - Neither team's calendar changes here. Each picks the move up on its
          next run, which is why both need re-planning afterwards — the service
          says so in its log line.
    """
    logger.info(
        "Moving quote %s to team %s at the request of %s.",
        quote_id,
        payload.team_id,
        caller.email,
    )
    return await service.reassign_team(quote_id, payload.team_id, caller)


@router.get("/{quote_id}", response_model=Quote)
async def get_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Return one quote, with its lines and weekly totals.

    Args:
        quote_id (str): The quote to read.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The quote.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
    """
    return await service.get(quote_id)


@router.get("/{quote_id}/aggregates", response_model=List[QuoteTypeWeekAggregate])
async def get_quote_aggregates(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> List[QuoteTypeWeekAggregate]:
    """Return a quote's totals, grouped by intervention type and by week.

    Args:
        quote_id (str): The quote to summarise.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[QuoteTypeWeekAggregate]: The totals, in display order.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.

    Notes:
        Served separately as well as inline on the quote, so a summary view can
        fetch the weekly breakdown without pulling every line.
    """
    quote = await service.get(quote_id)
    return quote.sorted_aggregates()


@router.put("/{quote_id}/lines", response_model=Quote)
async def replace_quote_lines(
    quote_id: str,
    payload: QuoteLinesRequest,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Replace a draft quote's lines and reprice it.

    Args:
        quote_id (str): The quote to change.
        payload (QuoteLinesRequest): The services that replace the stored
            ones.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The repriced quote.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteNotEditable: If the quote is past draft. Answered as a 409.
        MTPricingUnknownInterventionType: If a line names an unknown type;
            answered as a 422.

    Notes:
        Only the lines are taken from the body. The customer and the status
        stay as stored, so editing lines cannot reassign the quote or accept it
        on the customer's behalf.
    """
    return await service.replace_lines(quote_id, payload.lines)


@router.patch("/{quote_id}", response_model=Quote)
async def update_quote_header(
    quote_id: str,
    payload: QuoteHeaderRequest,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Change a quote's reference, customer, dates and renewal flag.

    Args:
        quote_id (str): The quote to change.
        payload (QuoteHeaderRequest): The header as it should now read.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The updated quote.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.

    Notes:
        Everything a screen shows about a quote is editable somewhere, and
        this route holds the part that is neither a line nor a status. The
        lines have their own route because replacing them reprices the quote;
        the status has one route per transition, because "send", "validate"
        and "accept" mean different things and are not interchangeable with
        setting a field.

        Unlike the lines route, this one is **not** restricted by status. A
        quote the planner sent back for validation is exactly the one somebody
        needs to correct, and it is past draft by definition.
    """
    return await service.update_header(
        quote_id,
        payload.reference,
        payload.customer_id,
        payload.issued_on,
        payload.valid_until,
        payload.auto_renew,
    )


@router.post("/{quote_id}/price", response_model=Quote)
async def reprice_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Recompute a draft quote's amounts against the current catalog.

    Args:
        quote_id (str): The quote to reprice.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The repriced quote.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteNotEditable: If the quote is past draft. Answered as a 409.
        MTPricingUnknownInterventionType: If a line names an unknown type;
            answered as a 422.

    Notes:
        Drafts only. An issued quote keeps the figures the customer was shown,
        even after the catalog moves under it.
    """
    return await service.reprice(quote_id)


@router.post("/{quote_id}/validate", response_model=Quote)
async def validate_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Approve a quote an assistant submitted, committing its work.

    Args:
        quote_id (str): The quote to validate.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the account that approved the figures.

    Returns:
        Quote: The validated quote, accepted and schedulable.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteNotEditable: If the quote is not awaiting validation. Answered
            as a 409.
        MTQuoteNotPriced: If the quote has no priced lines. Answered as a 409.

    Notes:
        - **Manager-gated, and that is the whole point of the status.** An
          assistant knows what a customer needs but does not set the agency's
          prices, so the quote they wrote waits here until somebody who does
          agrees to it. Who agreed is recorded on the quote.
        - **Validation accepts the quote**, so this is the moment its lines
          enter the planning computation — the same thing ``POST /{id}/send``
          does for a manager's own hand-written one. It used to stop at
          ``sent`` and need a second, separate acceptance, which nothing on any
          screen asked for: the quote left the validation queue and its work
          silently never reached a run.
    """
    logger.info("Validating quote %s at the request of %s.", quote_id, caller.email)
    validated = await service.validate(quote_id, validator_id=caller.id or caller.email)
    await publisher.publish(
        EventRoutingKey.QUOTE_VALIDATED,
        caller.company_id,
        {
            "quote_id": validated.id,
            "reference": validated.reference,
            "author_id": validated.authored_by,
            # Carried in the payload as well as the routing key: the key chooses
            # the queue and is gone by the time a handler reads the message, and
            # the handler needs the agency again to announce what it wrote.
            "company_id": caller.company_id,
        },
    )
    return validated


@router.post("/{quote_id}/refuse-validation", response_model=Quote)
async def refuse_quote_validation(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Send a submitted quote back to its author.

    Args:
        quote_id (str): The quote to send back.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the account that ruled.

    Returns:
        Quote: The quote, back in draft and editable again.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteNotEditable: If the quote is not awaiting validation. Answered
            as a 409.

    Notes:
        Distinct from ``/reject``, which records that the **customer** declined.
        This one records that the agency will not make the offer as written, and
        returns it to the assistant to correct.
    """
    logger.warning("Refusing quote %s at the request of %s.", quote_id, caller.email)
    refused = await service.refuse_validation(
        quote_id, validator_id=caller.id or caller.email
    )
    await publisher.publish(
        EventRoutingKey.QUOTE_REFUSED,
        caller.company_id,
        {
            "quote_id": refused.id,
            "reference": refused.reference,
            "author_id": refused.authored_by,
            "company_id": caller.company_id,
        },
    )
    return refused


@router.post("/{quote_id}/send", response_model=Quote)
async def send_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Issue a hand-written quote to the customer, agreed as it goes out.

    Args:
        quote_id (str): The quote to send.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the account that agreed to the figures.

    Returns:
        Quote: The issued quote, accepted and schedulable.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteNotPriced: If the quote has no priced lines. Answered as a 409.
        MTQuoteNotEditable: If the quote is past draft. Answered as a 409.

    Notes:
        Sending accepts the quote, so this is the moment its lines are
        committed to the planning computation. Manager-gated for that reason:
        the credential that sends is the one recorded as having agreed.
    """
    logger.info("Sending quote %s at the request of %s.", quote_id, caller.email)
    return await service.send(quote_id, validator_id=caller.id or caller.email)


@router.post("/{quote_id}/accept", response_model=Quote)
async def accept_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Record a customer's acceptance of a quote.

    Args:
        quote_id (str): The quote to accept.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The updated quote.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
        MTQuoteNotPriced: If the quote has no priced lines. Answered as a 409.

    Notes:
        This is the moment work is committed to: an accepted quote's lines are
        what the planning computation schedules.
    """
    return await service.accept(quote_id)


@router.post("/{quote_id}/reject", response_model=Quote)
async def reject_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Record a customer's refusal of a quote.

    Args:
        quote_id (str): The quote to reject.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The updated quote.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.
    """
    return await service.reject(quote_id)


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_admin_user),
) -> None:
    """Remove a quote and its lines.

    Args:
        quote_id (str): The quote to remove.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces administrator access.

    Raises:
        MTQuoteNotFound: If no such quote exists. Answered as a 404.

    Notes:
        - **Administrator-gated, not manager-gated**, unlike every other route
          here. A manager moves a quote through its lifecycle — validates it,
          refuses it, records that the customer rejected it — and each of those
          leaves a record of what was offered. This one destroys the record, so
          it sits a rank higher.
        - Rejecting a quote is not deleting it. This exists for the quotes that
          were never part of the agency's history: one raised in error, and the
          fixtures a test campaign is obliged to remove after itself. The QA
          campaign's teardown calls exactly this, which is why its absence left
          every run's fixtures behind for good.
    """
    logger.info("Deleting quote %s at the request of %s.", quote_id, caller.email)
    await service.delete(quote_id)


@router.get(
    "/{quote_id}/document",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_quote_document(
    quote_id: str,
    service: QuoteDocumentService = Depends(get_quote_document_service),
    caller: User = Depends(get_manager_user),
) -> Response:
    """Serve one quote as a PDF.

    Args:
        quote_id (str): The quote to render.
        service (QuoteDocumentService): The document service.
        caller (User): The authenticated caller; supplies the language.

    Returns:
        Response: The document, as ``application/pdf``.

    Raises:
        MTQuoteNotFound: If no such quote exists. A 404.
        MTQuoteNotPriced: If it has never been priced. A 422.
        MTQuoteRenderFailed: If the document could not be laid out. A 500.

    Notes:
        - **Rendered on demand, not read from a bucket.** Unlike an invoice, a
          quote is still an offer: it is re-priced when a rate changes and its
          lines are edited. A stored file would go stale silently and somebody
          would download last month's prices.
        - Written in the **caller's** language. A manager checking what a
          household will receive reads it in their own. The portal route below
          uses the household's.
        - ``response_model=None`` because the body is bytes — without it FastAPI
          tries to serialise the PDF as JSON. The ``responses`` block keeps the
          OpenAPI schema honest about the content type.
    """
    logger.info("%s is downloading quote %s.", caller.email, quote_id)
    payload, filename = await service.document(quote_id, language=caller.language)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
