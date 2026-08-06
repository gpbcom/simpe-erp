from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_current_user,
    get_customer_service,
    get_event_publisher,
    get_hca_service,
    get_quote_service,
)
from models.auth.user import User
from models.enums import EventRoutingKey
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.hca_profile_update_request import (
    HcaProfileUpdateRequest,
)
from models.schemas.responses.hca_response import HcaResponse
from service.customers.customers import CustomerService
from service.hcas.exceptions import MTHcaForbidden
from service.hcas.hcas import HcaService
from service.messaging.publisher import EventPublisher
from service.quotes.quotes import QuoteService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/me", tags=["My account"])


def _own_hca_id(caller: User) -> str:
    """Return the assistant record the caller owns, or refuse.

    Args:
        caller (User): The authenticated caller.

    Returns:
        str: The caller's assistant identifier.

    Raises:
        MTHcaForbidden: If the account is bound to no assistant record.

    Notes:
        A manager's account has no ``hca_id``. These routes are about *being* an
        assistant rather than about managing them, so a manager calling them is
        refused with an explanation rather than silently served an empty list —
        which would read as "you have no customers" rather than "this is not
        your screen".
    """
    if not caller.hca_id:
        logger.warning(
            "Account %s reached a self-service route but is bound to no "
            "assistant record.",
            caller.email,
        )
        raise MTHcaForbidden("This account is not linked to an assistant record.")
    return caller.hca_id


@router.get("/hca", response_model=HcaResponse)
async def read_my_profile(
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> HcaResponse:
    """Return the caller's own assistant record.

    Args:
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Returns:
        HcaResponse: The caller's own record.

    Raises:
        MTHcaForbidden: If the account is bound to no assistant record;
            answered as a 403.
        MTHcaNotFound: If the record has since been deleted; answered as a 404.
    """
    hca = await service.get(_own_hca_id(caller))
    return HcaResponse.from_hca(hca)


@router.patch("/hca", response_model=HcaResponse)
async def update_my_profile(
    request: HcaProfileUpdateRequest,
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> HcaResponse:
    """Change the caller's own contact details and address.

    Args:
        request (HcaProfileUpdateRequest): The new details.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Returns:
        HcaResponse: The updated record.

    Raises:
        MTHcaForbidden: If the account is bound to no assistant record;
            answered as a 403.
        MTHcaNotFound: If the record does not exist; answered as a 404.

    Notes:
        **The contract type and the certifications cannot be changed here**, and
        not because this endpoint ignores them — the payload has no such fields.
        What an assistant is employed as, and what they are qualified to do, are
        a manager's decisions, made through
        ``PATCH /api/v1/hcas/{id}/employment``. An assistant who could grant
        themselves a certification could be routed to work they are not trained
        for.
    """
    hca_id = _own_hca_id(caller)
    logger.info("Assistant %s is updating their own details.", hca_id)
    updated = await service.update_profile(
        hca_id=hca_id,
        first_name=request.first_name,
        last_name=request.last_name,
        phone_number=str(request.phone_number),
        email=str(request.email),
        address=request.address,
    )
    return HcaResponse.from_hca(updated)


@router.get("/customers", response_model=List[Customer])
async def list_my_customers(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    search: Optional[str] = Query(default=None),
    service: CustomerService = Depends(get_customer_service),
    caller: User = Depends(get_current_user),
) -> List[Customer]:
    """Return the customers the caller serves.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        search (Optional[str]): Restrict by name or address.
        service (CustomerService): The customer service.
        caller (User): The authenticated caller.

    Returns:
        List[Customer]: The caller's own customer portfolio.

    Raises:
        MTHcaForbidden: If the account is bound to no assistant record;
            answered as a 403.

    Notes:
        The portfolio is the customers the assistant has a planned visit with,
        plus those on quotes they wrote. It is **not** the agency's customer
        directory: a home-care record carries an address, a telephone number and
        a care schedule, and there is no reason for every assistant to hold every
        one of them.
    """
    return await service.list_for_hca(
        hca_id=_own_hca_id(caller),
        account_id=caller.id or caller.email,
        page=page,
        size=size,
        search=search,
    )


@router.get("/customers/{customer_id}", response_model=Customer)
async def read_my_customer(
    customer_id: str,
    service: CustomerService = Depends(get_customer_service),
    caller: User = Depends(get_current_user),
) -> Customer:
    """Return one customer from the caller's portfolio.

    Args:
        customer_id (str): The customer to read.
        service (CustomerService): The customer service.
        caller (User): The authenticated caller.

    Returns:
        Customer: The customer.

    Raises:
        MTHcaForbidden: If the account is bound to no assistant record;
            answered as a 403.
        MTCustomerNotFound: If the customer does not exist **or** is not in the
            caller's portfolio; answered as a 404 either way.

    Notes:
        The same 404 whether the customer is absent or simply not theirs.
        Distinguishing the two would let an assistant discover which identifiers
        are real by trying them.
    """
    return await service.get_for_hca(
        customer_id,
        hca_id=_own_hca_id(caller),
        account_id=caller.id or caller.email,
    )


@router.get("/quotes", response_model=List[Quote])
async def list_my_quotes(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_current_user),
) -> List[Quote]:
    """Return the quotes the caller wrote.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller.

    Returns:
        List[Quote]: The caller's own quotes, whatever their status.
    """
    return await service.list(
        page=page, size=size, authored_by=caller.id or caller.email
    )


@router.post("/quotes", response_model=Quote, status_code=status.HTTP_201_CREATED)
async def create_my_quote(
    quote: Quote,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_current_user),
) -> Quote:
    """Write a quote, as a draft the caller still owns.

    Args:
        quote (Quote): The quote to create.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller.

    Returns:
        Quote: The stored, priced quote.

    Raises:
        MTPricingUnknownInterventionType: If a line names a type that is not in
            the catalog; answered as a 422.

    Notes:
        It is created as a **draft**, not submitted. Writing a quote and
        deciding it is ready are two separate acts, and an assistant pricing up
        a visit while sitting with a family should be able to save it and check
        the figures before a manager is asked to look.
    """
    return await service.create(quote, author_id=caller.id or caller.email)


@router.post("/quotes/{quote_id}/submit", response_model=Quote)
async def submit_my_quote(
    quote_id: str,
    service: QuoteService = Depends(get_quote_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_current_user),
) -> Quote:
    """Send one of the caller's own drafts for validation.

    Args:
        quote_id (str): The quote to submit.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller.

    Returns:
        Quote: The submitted quote, now awaiting a manager.

    Raises:
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteForbidden: If the caller did not write it; answered as a 403.
        MTQuoteNotEditable: If it is not a draft; answered as a 409.
        MTQuoteNotPriced: If it has no priced lines; answered as a 409.
    """
    logger.info("Assistant %s is submitting quote %s.", caller.email, quote_id)
    submitted = await service.submit_for_validation(
        quote_id, author_id=caller.id or caller.email
    )
    # Published after the quote is stored, never instead of storing it. The
    # manager's queue is a database query on ``status=pending-validation``, so
    # a lost message costs the push notification and nothing else.
    await publisher.publish(
        EventRoutingKey.QUOTE_SUBMITTED,
        {
            "quote_id": submitted.id,
            "reference": submitted.reference,
            "author_id": caller.id,
            "author_name": caller.full_name,
            "company_id": caller.company_id,
        },
    )
    return submitted
