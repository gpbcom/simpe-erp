from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import get_customer_service, get_manager_user
from models.auth.user import User
from models.enums import RegistrationStatus
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.status_update_request import StatusUpdateRequest
from service.customers.customers import CustomerService

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


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
    _: User = Depends(get_manager_user),
) -> None:
    """Remove a customer who has never been quoted.

    Args:
        customer_id (str): The customer to remove.
        service (CustomerService): The customer service.
        _ (User): The authenticated caller; enforces manager access.

    Raises:
        MTCustomerNotFound: If no such customer exists; answered as a 404.
        MTCustomerHasQuotes: If any quote names them; answered as a 409, with
            stopping them offered instead.
    """
    logger.info("Deleting customer %s.", customer_id)
    await service.delete(customer_id)
