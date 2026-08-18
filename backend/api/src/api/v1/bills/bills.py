from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, Response

# First-party imports
from api.dependencies import (
    get_billing_service,
    get_event_publisher,
    get_manager_user,
)
from models.auth.user import User
from models.billing.bill import Bill
from models.enums import BillStatus, EventRoutingKey
from models.schemas.requests.billing.bill_filter import BillFilter
from models.schemas.requests.billing.bill_status_request import BillStatusRequest
from service.billing.billings import BillingService
from service.messaging.publisher import EventPublisher

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/bills", tags=["Bills"])


@router.get("", response_model=List[Bill])
async def list_bills(
    page: int = Query(default=1, ge=1),
    size: Optional[int] = Query(default=None, ge=1, le=200),
    search: Optional[str] = Query(default=None),
    number: Optional[str] = Query(default=None),
    customer_id: Optional[str] = Query(default=None),
    bill_status: Optional[str] = Query(default=None, alias="status"),
    is_sent: Optional[bool] = Query(default=None),
    period_start: Optional[str] = Query(default=None),
    period_end: Optional[str] = Query(default=None),
    service: BillingService = Depends(get_billing_service),
    caller: User = Depends(get_manager_user),
) -> List[Bill]:
    """List an agency's invoices, most recent period first.

    Args:
        page (int): One-based page number.
        size (Optional[int]): Page size.
        search (Optional[str]): Fragment matched against the invoice number.
        number (Optional[str]): Fragment of the invoice number.
        customer_id (Optional[str]): Restrict to one customer's invoices.
        bill_status (Optional[str]): Restrict to one commercial status.
        is_sent (Optional[bool]): Restrict by whether the customer was
            emailed.
        period_start (Optional[str]): Only windows starting on or after this
            day.
        period_end (Optional[str]): Only windows ending on or before this day.
        service (BillingService): The billing service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        List[Bill]: The matching invoices.

    Notes:
        - The **enum and the date** parameters arrive as strings and are
          coerced by
          :class:`~models.schemas.requests.billing.bill_filter.BillFilter`,
          which is what lets a cleared control submit ``""`` and mean "not
          applied". Declared as the enum or the date, FastAPI would reject the
          empty string before the filter's own validator ever ran, and the
          screen would answer 422 every time somebody cleared a box.
        - **The flag is the exception and is typed**, so FastAPI coerces
          ``?is_sent=true`` before it reaches the shared
          :meth:`~models.base.entity_filter.EntityFilter.validate_flag`, which
          accepts only a boolean or nothing. A cleared flag is dropped from the
          query rather than emptied — the contract every other list screen
          already has.
        - The agency comes from the credential and is applied in the statement.
          A filter that could widen its own scope would show one customer's
          money to a manager entitled to another's.
    """
    applied = BillFilter(
        search=search,
        number=number,
        customer_id=customer_id,
        status=bill_status,
        is_sent=is_sent,
        period_start=period_start,
        period_end=period_end,
    )
    return await service.list(
        caller.company_id, page=page, size=size, bill_filter=applied
    )


@router.get("/{bill_id}", response_model=Bill)
async def get_bill(
    bill_id: str,
    service: BillingService = Depends(get_billing_service),
    _: User = Depends(get_manager_user),
) -> Bill:
    """Return one invoice with its charges.

    Args:
        bill_id (str): The invoice to read.
        service (BillingService): The billing service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Bill: The invoice.

    Raises:
        MTBillNotFound: When there is no such invoice. Answered as a 404 by the
            central handler.
    """
    return await service.get(bill_id)


@router.patch("/{bill_id}/status", response_model=Bill)
async def set_bill_status(
    bill_id: str,
    request: BillStatusRequest,
    service: BillingService = Depends(get_billing_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> Bill:
    """Move an invoice along its commercial lifecycle.

    Args:
        bill_id (str): The invoice to move.
        request (BillStatusRequest): The status to move it to.
        service (BillingService): The billing service.
        publisher (EventPublisher): Announces an approved invoice.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        Bill: The updated invoice.

    Raises:
        MTBillNotFound: When there is no such invoice. Answered as a 404.
        MTBillTransitionNotAllowed: When the move skips a step. Answered as a
            409.

    Notes:
        - **Manager or administrator only**, which is the specification's own
          rule: the status is a statement about money owed, and an assistant who
          could set one would be writing the agency's accounts.
        - **Moving to ``accepted`` is what sends the invoice.** The event is
          published after the record says a human approved it, never before —
          which is the whole reason a generation run leaves every invoice
          waiting rather than emailing as it goes.
        - A failed publish is logged and the call still succeeds. The approval
          is real and stored. The invoice simply stays at ``accepted``, which
          reads as "approved but not yet out" and is actionable.
    """
    actor = caller.id if caller.id else caller.email
    updated = await service.set_status(bill_id, request.status, actor)
    if updated.status is BillStatus.PAID:
        # A settled invoice is a reportable event: VAT on services falls due on
        # collection, so "paid" is the moment the tax authority wants declared.
        # Announced rather than transmitted inline, for the same reason approval
        # is — a platform on the other side of the internet must not sit in
        # front of a manager's click.
        collected = await publisher.publish(
            EventRoutingKey.BILL_PAID,
            caller.company_id,
            {"bill_id": bill_id, "company_id": caller.company_id},
        )
        if not collected:
            logger.error(
                "Invoice %s was marked paid but could not be announced. It will "
                "not reach the certified platform until it is re-published.",
                updated.number,
            )
        return updated
    if updated.status is not BillStatus.ACCEPTED:
        return updated
    announced = await publisher.publish(
        EventRoutingKey.BILL_ACCEPTED,
        caller.company_id,
        {"bill_id": bill_id, "company_id": caller.company_id},
    )
    if not announced:
        logger.error(
            "Invoice %s was approved but could not be announced. It stays at "
            "accepted until it is re-published.",
            updated.number,
        )
    return updated


@router.get(
    "/{bill_id}/document",
    response_class=Response,
    response_model=None,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def download_bill_document(
    bill_id: str,
    service: BillingService = Depends(get_billing_service),
    _: User = Depends(get_manager_user),
) -> Response:
    """Stream one invoice's PDF.

    Args:
        bill_id (str): The invoice to download.
        service (BillingService): The billing service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Response: The document, as an attachment.

    Raises:
        MTBillNotFound: When there is no such invoice. Answered as a 404.
        MTBillDocumentUnavailable: When the document cannot be read. Answered
            as a 503.

    Notes:
        - **Streamed through this endpoint rather than served from the bucket.**
          The objects are written under a private prefix precisely so the bearer
          guard is the only way to them; redirecting to a presigned URL would
          put a customer's invoice outside it.
        - ``response_model=None`` because the body is bytes: without it FastAPI
          tries to serialise the PDF as JSON. The ``responses`` block is what
          keeps the OpenAPI schema honest about the content type, since there is
          no model to infer it from.
        - The filename is derived from the invoice number by the service, never
          from anything the caller sends.
    """
    payload, filename = await service.document(bill_id)
    logger.info("Serving %d bytes of %s.", len(payload), filename)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/customers/{customer_id}", response_model=Bill)
async def bill_one_customer(
    customer_id: str,
    reference_date: date = Query(...),
    service: BillingService = Depends(get_billing_service),
    caller: User = Depends(get_manager_user),
) -> Bill:
    """Bill a single customer for the period containing a day.

    Args:
        customer_id (str): The customer to bill.
        reference_date (date): Any day inside the period.
        service (BillingService): The billing service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        Bill: The issued invoice.

    Raises:
        MTBillAlreadyIssued: When the period is billed already. Answered as a
            409.
        MTBillNothingToBill: When the customer owes nothing. Answered as a 409.

    Notes:
        - Behind a **static** ``customers`` segment, not ``/{customer_id}``
          directly. A bare identifier there would be matched by the same pattern
          as ``/{bill_id}``, and the router would resolve whichever it met
          first — a collision invisible until somebody's customer identifier
          started returning an invoice.
        - Synchronous, unlike a whole run, because it produces one document and
          a caller who named one customer is waiting for the answer. It is also
          the one path where an empty or already-billed period is an **error**
          rather than a customer to pass over: a run over everybody skips both
          silently, since most customers have no work in most weeks.
    """
    return await service.bill_one(
        company_id=caller.company_id,
        customer_id=customer_id,
        reference_date=reference_date,
        actor=caller.id if caller.id else caller.email,
        language=caller.language,
    )
