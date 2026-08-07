from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, Response, status

# First-party imports
from api.dependencies import (
    get_customer_service,
    get_event_publisher,
    get_manager_user,
    get_planning_service,
)
from models.auth.user import User
from models.enums import RegistrationStatus
from models.people.customer import Customer
from models.planning.planning_run import PlanningRun
from models.quoting.quote import Quote
from models.schemas.requests.customers.status_update_request import StatusUpdateRequest
from service.customers.customers import CustomerService
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
    search: Optional[str] = Query(default=None),
    registration_status: Optional[RegistrationStatus] = Query(
        default=None, alias="status"
    ),
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> List[Customer]:
    """List customers.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        search (Optional[str]): Case-insensitive fragment of a name.
        registration_status (Optional[RegistrationStatus]): Restrict to one
            status.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[Customer]: The matching customers.
    """
    logger.debug("Listing customers: page=%d search=%r.", page, search)
    return await service.list(
        page=page, size=size, search=search, status=registration_status
    )


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
