from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError

# First-party imports
from api.dependencies import (
    get_customer_service,
    get_event_publisher,
    get_manager_user,
    get_planning_service,
)
from models.auth.user import User
from models.people.customer import Customer
from models.planning.planning_run import PlanningRun
from models.quoting.quote import Quote
from models.schemas.requests.customers.customer_filter import CustomerFilter
from models.schemas.requests.customers.status_update_request import StatusUpdateRequest
from service.customers.customers import CustomerService
from service.customers.exceptions import MTCustomerNotPromotable
from service.messaging.publisher import EventPublisher
from service.planning.plannings import PlanningService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])


@router.post("", response_model=Customer, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer: Customer,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> Customer:
    """Register a customer.

    Args:
        customer (Customer): The customer to register.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Customer: The stored customer, with its identifier.

    Notes:
        The address resolves its own coordinate while the payload is validated,
        so this call may wait on the geocoding service. A street the map does
        not know is still accepted; the failure is recorded on the address.
    """
    logger.info("Creating a customer.")
    return await service.create(customer)


@router.get("", response_model=List[Customer])
async def list_customers(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    customer_filter: CustomerFilter = Depends(),
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> List[Customer]:
    """List customers, narrowed by whichever filters were sent.

    Args:
        customer_filter (CustomerFilter): The filters, bound from the query
            string. Every field is optional and an absent one narrows nothing.
        page (int): One-based page number.
        size (int): Page size.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[Customer]: The matching customers.

    Raises:
        MTInvalidCustomerFilterException: If a filter is malformed; answered as
            a 422.

    Notes:
        - **The filters are a model, not eight parameters.** The signature was
          already at four and the screen now sends eight; gathering them puts
          the validation somewhere unit tests can reach without an HTTP client,
          and stops the router growing a paragraph of ``Query`` defaults.
        - Bound with ``Depends()`` rather than ``Annotated[..., Query()]``.
          Both are documented, but only the former **flattens** the model into
          individual query parameters here — the latter binds it as one
          parameter called ``customer_filter`` taking a JSON object, which
          answers 422 to every request the screen sends. ``Depends()`` also
          coerces each field before the model sees it, so ``?is_geocoded=false``
          arrives as a boolean and the model's strict flag validator keeps
          guarding what it is for: a filter built by hand in Python.
        - ``?search=`` and ``?status=`` keep the names and meanings they had, so
          nothing that called this before has to change.
        - Filtering happens **here**, not in the browser. The grid asks for one
          page; a client-side filter would search only the rows it happens to
          hold and silently miss the rest of the book.
    """
    logger.debug(
        "Listing customers: page=%d size=%d filter=%s.",
        page,
        size,
        customer_filter.model_dump(exclude_none=True),
    )
    if customer_filter.is_empty():
        logger.debug("No filter was sent; listing the whole book.")
    if size >= 200:
        # The screen asks for 200. Anything at or above that is a page nobody
        # reads to the end of, and it scans the whole table to build.
        logger.warning("A page of %d customers was asked for.", size)
    try:
        customers = await service.list(
            page=page, size=size, customer_filter=customer_filter
        )
    except SQLAlchemyError:
        logger.error(
            "Listing customers failed for filter=%s.",
            customer_filter.model_dump(exclude_none=True),
        )
        raise
    logger.info("Answering with %d customers.", len(customers))
    return customers


@router.get("/{customer_id}", response_model=Customer)
async def get_customer(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> Customer:
    """Return one customer.

    Args:
        customer_id (str): The customer to read.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Customer: The customer.

    Raises:
        MTCustomerNotFound: If no such customer exists; answered as a 404.
    """
    logger.debug("Reading customer %s.", customer_id)
    return await service.get(customer_id)


@router.put("/{customer_id}", response_model=Customer)
async def update_customer(
    customer_id: str,
    customer: Customer,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> Customer:
    """Replace a customer's details.

    Args:
        customer_id (str): The customer to change.
        customer (Customer): The new details.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Customer: The updated customer.

    Raises:
        MTCustomerNotFound: If no such customer exists; answered as a 404.

    Notes:
        The path identifier wins over anything in the body — a payload naming a
        different customer edits the one that was addressed, not the one it
        names.
    """
    logger.info("Updating customer %s.", customer_id)
    return await service.update(customer_id, customer)


@router.patch("/{customer_id}/status", response_model=Customer)
async def set_customer_status(
    customer_id: str,
    payload: StatusUpdateRequest,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> Customer:
    """Activate or stop a customer.

    Args:
        customer_id (str): The customer to change.
        payload (StatusUpdateRequest): The status to set.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Customer: The updated customer.

    Raises:
        MTCustomerNotFound: If no such customer exists; answered as a 404.

    Notes:
        A single-field payload rather than a full customer: this is the one
        change a manager makes without touching anything else, and a whole
        customer in the body would let a stale copy overwrite the address.
    """
    logger.info(
        "Setting customer %s to %s.", customer_id, payload.registration_status.value
    )
    return await service.set_status(customer_id, payload.registration_status)


@router.post("/{customer_id}/promote", response_model=Customer)
async def promote_customer(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> Customer:
    """Promote a prospect to an active customer.

    Args:
        customer_id (str): The customer to promote.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Customer: The promoted customer.

    Raises:
        MTCustomerNotFound: If no such customer exists; answered as a 404.
        MTCustomerNotPromotable: If they are not a prospect; answered as a 409.

    Notes:
        - **The act that puts a customer into the planning.** A prospect may
          already hold accepted, priced work that every run has deliberately
          left out; this is what enters it into the next one. A named route
          rather than one value among three on ``PATCH /{id}/status``, so the
          rule that only a prospect may be promoted lives in one place and the
          log line says *promoted* rather than *status changed*.
        - **No payload.** There is exactly one status a promotion can lead to,
          so a body carrying it would only be a way to ask for a different one.
        - Manager access, which is manager **and** administrator: roles are
          ranked and an administrator outranks a manager. Deciding that the
          agency will serve somebody is running the agency's work, which is
          what a manager is for.
    """
    logger.debug("Promotion requested for customer %s.", customer_id)
    logger.info("Promoting customer %s.", customer_id)
    try:
        promoted = await service.promote(customer_id)
    except MTCustomerNotPromotable:
        # A 409, and worth a line of its own: it is what two managers pressing
        # the button at once looks like, and it is the only failure here that
        # is nobody's mistake.
        logger.warning("Customer %s was not a prospect; nothing changed.", customer_id)
        raise
    except SQLAlchemyError:
        logger.error("Writing the promotion of customer %s failed.", customer_id)
        raise
    return promoted


@router.get("/{customer_id}/quotes", response_model=List[Quote])
async def list_customer_quotes(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> List[Quote]:
    """Return every quote issued to a customer.

    Args:
        customer_id (str): The customer to read.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[Quote]: Their quotes.

    Raises:
        MTCustomerNotFound: If no such customer exists; answered as a 404.
    """
    logger.debug("Listing the quotes of customer %s.", customer_id)
    return await service.quotes_for(customer_id)


@router.delete(
    "/{customer_id}",
    response_model=Optional[PlanningRun],
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_customer(
    customer_id: str,
    response: Response,
    service: CustomerService = Depends(get_customer_service),
    plannings: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> Optional[PlanningRun]:
    """Remove a customer, every quote written for them, and replan.

    Args:
        customer_id (str): The customer to remove.
        response (Response): The response being built, so the status can drop
            to 204 when there is nothing to replan.
        service (CustomerService): The customer service.
        plannings (PlanningService): Records the replan.
        publisher (EventPublisher): Queues the solve for a worker.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        Optional[PlanningRun]: The pending replan with the identifier to poll,
        or ``None`` when the customer had no future visits.

    Raises:
        MTCustomerNotFound: If no such customer exists; answered as a 404.
        MTCustomerHasQuotes: If a quote of theirs cannot be identified and so
            cannot be removed with them; answered as a 409.

    Notes:
        - **This destroys billing history**, and the screen offering it says
          how much before asking. Stopping a customer remains the right answer
          for one who was really served and has really left; this is for a
          household entered by mistake, and for the fixtures a test campaign
          removes after itself.
        - **The period is measured before the delete.** Their visits go with
          their quotes, so asking afterwards would find nothing and replan
          nothing — leaving every assistant who was due to visit them holding a
          gap that no other work has been moved into.
    """
    period = await plannings.future_period_for_customer(customer_id)
    await service.delete(customer_id)
    logger.info("%s deleted customer %s.", caller.email, customer_id)
    if period is None:
        logger.info(
            "Customer %s had no future visit; no replan is queued.", customer_id
        )
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return await plannings.queue_replan(
        requested_by=caller.id or caller.email,
        company_id=caller.company_id,
        period=period,
        publisher=publisher,
        reason=f"customer {customer_id} was removed",
    )
