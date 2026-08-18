from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_billing_service,
    get_event_publisher,
    get_manager_user,
)
from models.auth.user import User
from models.billing.billing_run import BillingRun
from models.enums import EventRoutingKey
from models.schemas.requests.billing.bill_generation_request import (
    BillGenerationRequest,
)
from service.billing.billings import BillingService
from service.messaging.publisher import EventPublisher

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/bills", tags=["Billing runs"])


@router.post("/runs", response_model=BillingRun, status_code=status.HTTP_202_ACCEPTED)
async def start_billing_run(
    request: BillGenerationRequest,
    service: BillingService = Depends(get_billing_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> BillingRun:
    """Bill the period containing a day.

    Args:
        request (BillGenerationRequest): The day inside the period to bill.
        service (BillingService): The billing service.
        publisher (EventPublisher): Queues the generation for a worker.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        BillingRun: The pending run, with the identifier to poll.

    Raises:
        MTBillingPeriodInFuture: When the period has not finished. Answered as
            a 422 by the central handler.
        MTBillingSettingsUnavailable: When the invoicing rules cannot be read;
            answered as a 503.

    Notes:
        - Answers **202**, not 200. A monthly close over three hundred customers
          is three hundred documents rendered and three hundred objects
          uploaded; holding the request open for that would tie up a connection
          and time out the client. Poll ``GET /runs/{id}`` until the status is
          terminal.
        - The run is **recorded before it is queued**, and the record is what
          the caller is given. If the broker is unreachable the run stays
          ``pending`` rather than vanishing: the identifier is real either way,
          and the work can be re-queued without anybody reconstructing what was
          asked for.
        - **A manager, not an administrator.** Billing is a manager's routine
          monthly job, where a planning run rewrites every assistant's calendar.
        - The caller names a **day**, never a window. The period is resolved
          from the agency's own periodicity, so nobody can invoice a fortnight
          the settings do not describe and produce a window no one could
          reproduce afterwards.
        - **Nothing is emailed by this.** The run renders every invoice and
          stops; each one waits for a manager to validate it, and validation is
          what sends it.
    """
    run = await service.request_run(
        company_id=caller.company_id,
        reference_date=request.reference_date,
        requested_by=caller.id if caller.id else caller.email,
    )
    logger.info(
        "Queued billing run %s for agency %s over %s..%s.",
        run.id,
        caller.company_id,
        run.period_start,
        run.period_end,
    )
    queued = await publisher.publish(
        EventRoutingKey.BILLING_RUN_REQUESTED,
        caller.company_id,
        {"run_id": run.id, "company_id": caller.company_id},
    )
    if not queued:
        logger.error(
            "Billing run %s was recorded but could not be queued. It stays "
            "pending until it is re-published.",
            run.id,
        )
    return run


@router.get("/runs", response_model=List[BillingRun])
async def list_billing_runs(
    page: int = Query(default=1, ge=1),
    size: Optional[int] = Query(default=None, ge=1, le=200),
    service: BillingService = Depends(get_billing_service),
    caller: User = Depends(get_manager_user),
) -> List[BillingRun]:
    """List an agency's billing runs, most recently requested first.

    Args:
        page (int): One-based page number.
        size (Optional[int]): Page size.
        service (BillingService): The billing service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        List[BillingRun]: The runs.

    Notes:
        Scoped to the caller's own agency in the service, not filtered
        afterwards: a page of runs narrowed after it is read has already loaded
        somebody else's month.
    """
    return await service.list_runs(caller.company_id, page=page, size=size)


@router.get("/runs/{run_id}", response_model=BillingRun)
async def get_billing_run(
    run_id: str,
    service: BillingService = Depends(get_billing_service),
    _: User = Depends(get_manager_user),
) -> BillingRun:
    """Return one billing run, so a caller can poll it.

    Args:
        run_id (str): The run to read.
        service (BillingService): The billing service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        BillingRun: The run.

    Raises:
        MTBillingRunNotFound: When there is no such run. Answered as a 404 by
            the central handler.

    Notes:
        Poll until :meth:`~models.billing.billing_run.BillingRun.is_terminal`.
        A **partial** run is finished — the invoices that could be written are
        written — so a client that kept polling would wait for ever.
    """
    return await service.get_run(run_id)
