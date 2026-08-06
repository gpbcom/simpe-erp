from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_event_publisher,
    get_manager_user,
    get_quote_service,
)
from models.auth.user import User
from models.enums import EventRoutingKey, QuoteStatus
from models.quoting.quote import Quote
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate
from service.messaging.publisher import EventPublisher
from service.quotes.quotes import QuoteService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/quotes", tags=["Quotes"])


@router.post("", response_model=Quote, status_code=status.HTTP_201_CREATED)
async def create_quote(
    quote: Quote,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_manager_user),
) -> Quote:
    """Create a quote and price whatever lines it arrives with.

    Args:
        quote (Quote): The quote to create.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the quote's author.

    Returns:
        Quote: The stored, priced quote with its weekly totals.

    Raises:
        MTPricingUnknownInterventionType: If a line names a type that is not in
            the catalog; answered as a 422.

    Notes:
        The author is taken from the credential, never from the payload. A
        manager's quote needs no validation step — they are the ones who would
        sign it off — so it lands as a draft ready to send.
    """
    return await service.create(quote, author_id=caller.id or caller.email)


@router.get("", response_model=List[Quote])
async def list_quotes(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    customer_id: Optional[str] = Query(default=None),
    quote_status: Optional[QuoteStatus] = Query(default=None, alias="status"),
    authored_by: Optional[str] = Query(default=None),
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> List[Quote]:
    """List quotes.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        customer_id (Optional[str]): Restrict to one customer.
        quote_status (Optional[QuoteStatus]): Restrict to one status.
        authored_by (Optional[str]): Restrict to one author's quotes.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[Quote]: The matching quotes.

    Notes:
        Filtering by ``status=pending-validation`` is what the manager's
        validation queue is: the quotes an assistant has submitted and nobody
        has ruled on yet.
    """
    return await service.list(
        page=page,
        size=size,
        customer_id=customer_id,
        status=quote_status,
        authored_by=authored_by,
    )


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
        MTQuoteNotFound: If no such quote exists; answered as a 404.
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
        MTQuoteNotFound: If no such quote exists; answered as a 404.

    Notes:
        Served separately as well as inline on the quote, so a summary view can
        fetch the weekly breakdown without pulling every line.
    """
    quote = await service.get(quote_id)
    return quote.sorted_aggregates()


@router.put("/{quote_id}/lines", response_model=Quote)
async def replace_quote_lines(
    quote_id: str,
    quote: Quote,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Replace a draft quote's lines and reprice it.

    Args:
        quote_id (str): The quote to change.
        quote (Quote): A quote carrying the new lines.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The repriced quote.

    Raises:
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteNotEditable: If the quote is past draft; answered as a 409.
        MTPricingUnknownInterventionType: If a line names an unknown type;
            answered as a 422.

    Notes:
        Only the lines are taken from the body. The customer and the status
        stay as stored, so editing lines cannot reassign the quote or accept it
        on the customer's behalf.
    """
    return await service.replace_lines(quote_id, quote)


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
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteNotEditable: If the quote is past draft; answered as a 409.
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
    """Approve a quote an assistant submitted, and issue it.

    Args:
        quote_id (str): The quote to validate.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the account that approved the figures.

    Returns:
        Quote: The validated quote, now sent.

    Raises:
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteNotEditable: If the quote is not awaiting validation; answered
            as a 409.
        MTQuoteNotPriced: If the quote has no priced lines; answered as a 409.

    Notes:
        **Manager-gated, and that is the whole point of the status.** An
        assistant knows what a customer needs but does not set the agency's
        prices, so the quote they wrote waits here until somebody who does
        agrees to it. Who agreed is recorded on the quote.
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
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteNotEditable: If the quote is not awaiting validation; answered
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
        },
    )
    return refused


@router.post("/{quote_id}/send", response_model=Quote)
async def send_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    _: User = Depends(get_manager_user),
) -> Quote:
    """Mark a priced quote as sent to the customer.

    Args:
        quote_id (str): The quote to send.
        service (QuoteService): The quote service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Quote: The updated quote.

    Raises:
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteNotPriced: If the quote has no priced lines; answered as a 409.
    """
    return await service.send(quote_id)


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
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteNotPriced: If the quote has no priced lines; answered as a 409.

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
        MTQuoteNotFound: If no such quote exists; answered as a 404.
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
        MTQuoteNotFound: If no such quote exists; answered as a 404.

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
