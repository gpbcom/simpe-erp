from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, File, Query, UploadFile, status

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_auth_service,
    get_company_service,
    get_current_user,
    get_customer_service,
    get_event_publisher,
    get_hca_service,
    get_quote_service,
)
from models.auth.user import User
from models.companies.company import Company
from models.enums import EventRoutingKey
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.account_update_request import AccountUpdateRequest
from models.schemas.requests.company_profile_update_request import (
    CompanyProfileUpdateRequest,
)
from models.schemas.requests.hca_profile_update_request import (
    HcaProfileUpdateRequest,
)
from models.schemas.responses.hca_response import HcaResponse
from models.schemas.responses.user_response import UserResponse
from service.auth.auth import AuthService
from service.companies.companies import CompanyService
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


@router.get("/company", response_model=Company)
async def read_my_company(
    service: CompanyService = Depends(get_company_service),
    caller: User = Depends(get_admin_user),
) -> Company:
    """Return the agency the caller administers.

    Args:
        service (CompanyService): The company service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        Company: The caller's own agency.

    Raises:
        MTCompanyNotFound: If the agency has since been deleted; 404.

    Notes:
        **The identifier comes from the credential**, so there is nothing to
        pass and nothing to point at somebody else's agency. That is the whole
        reason this route exists beside ``GET /api/v1/companies/{id}``: an
        administrator signing in to their own agency's screen has no way to
        know its identifier, and asking the browser to hold one it read from
        somewhere else is how a screen ends up editing the wrong tenant.
    """
    logger.info("Administrator %s read their own agency.", caller.email)
    return await service.get(caller.company_id)


@router.put("/company", response_model=Company)
async def update_my_company(
    request: CompanyProfileUpdateRequest,
    service: CompanyService = Depends(get_company_service),
    caller: User = Depends(get_admin_user),
) -> Company:
    """Change the details of the agency the caller administers.

    Args:
        request (CompanyProfileUpdateRequest): The details to store.
        service (CompanyService): The company service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        Company: The updated agency.

    Raises:
        MTCompanyNotFound: If the agency has since been deleted; 404.

    Notes:
        Administrator-only, not manager. A manager runs the agency's work; its
        legal identity — trading name, SIRET, registered address — is not part
        of running the week, and the one field with an outward effect
        (``is_accepting_applications``) decides whether strangers can apply.

        The existing agency is read before the write so the stored identifier
        and timestamps survive: the payload carries none of them, and building
        a fresh ``Company`` from it would blank whatever it does not mention.
    """
    logger.info("Administrator %s is updating their own agency.", caller.email)
    existing = await service.get(caller.company_id)
    return await service.update(
        caller.company_id,
        existing.model_copy(
            update={
                "name": request.name,
                "registration_number": request.registration_number,
                "contact_email": request.contact_email,
                "address": request.address,
                "is_accepting_applications": request.is_accepting_applications,
            }
        ),
    )


@router.get("/account", response_model=UserResponse)
async def read_my_account(
    caller: User = Depends(get_current_user),
) -> UserResponse:
    """Return the caller's own account.

    Args:
        caller (User): The authenticated caller.

    Returns:
        UserResponse: The account behind the credential, without its hash.

    Notes:
        **Guarded by ``get_current_user`` and nothing else**, so every signed-in
        account can read it — including a manager or an administrator, who have
        no assistant record and for whom every other route in this file is a
        403. Without it the account screen had nothing to show them: it was
        built on ``GET /me/hca``, so it rendered an error to exactly the people
        who could not fix it.

        There is no ``user_id``. The account returned is the one the credential
        names, so this route cannot be pointed at anybody else's.
    """
    logger.info("Account %s read its own details.", caller.email)
    return UserResponse.from_user(caller)


@router.patch("/account", response_model=UserResponse)
async def update_my_account(
    request: AccountUpdateRequest,
    service: AuthService = Depends(get_auth_service),
    caller: User = Depends(get_current_user),
) -> UserResponse:
    """Change the caller's own display name and sign-in address.

    Args:
        request (AccountUpdateRequest): The details to store.
        service (AuthService): The authentication service.
        caller (User): The authenticated caller.

    Returns:
        UserResponse: The updated account.

    Raises:
        MTAuthEmailAlreadyRegistered: If another account already uses that
            address; answered as a 409.

    Notes:
        The payload carries a display name and an address and **nothing else**
        — no role, no active flag, no company. That is the permission, written
        as a shape rather than as a check: see ``AccountUpdateRequest``.

        Changing the address changes what the holder signs in with. The token
        they already hold keeps working, because it names the account rather
        than the address, so the change does not sign them out mid-edit.
    """
    logger.info("Account %s is updating its own details.", caller.email)
    updated = await service.update_account(
        caller, full_name=request.full_name, email=request.email
    )
    return UserResponse.from_user(updated)


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
        - **The contract type, the certifications and the role cannot be changed
          here**, and not because this endpoint ignores them — the payload has
          no such fields. What an assistant is employed as and what they are
          qualified to do are a manager's decisions, made through
          ``PATCH /api/v1/hcas/{id}/employment``; what they are allowed to do is
          an administrator's, through ``POST /api/v1/users/{id}/promote``. An
          assistant who could grant themselves a certification could be routed
          to work they are not trained for.
        - A manager editing their **own** record reaches those two endpoints the
          same way they would for anybody else's, so this payload never widens
          for them. The screen decides which fields to offer; the server decides
          which it will accept, and the two are checked separately.
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
        driving_license=request.driving_license,
    )
    return HcaResponse.from_hca(updated)


@router.put("/hca/photo", response_model=HcaResponse)
async def replace_my_photo(
    photo: UploadFile = File(...),
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> HcaResponse:
    """Replace the caller's own photograph.

    Args:
        photo (UploadFile): The image to store.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Returns:
        HcaResponse: The updated record, carrying the new URL.

    Raises:
        MTHcaForbidden: If the account is bound to no assistant record;
            answered as a 403.
        MTS3UnsupportedContentType: If the bytes are not a JPEG, PNG or WebP;
            answered as a 415.
        MTS3PayloadTooLarge: If the image exceeds the configured limit;
            answered as a 413.

    Notes:
        An assistant's portrait **is their pin on the manager's map**, so being
        unable to set their own was a gap rather than a restriction: it left the
        one piece of personal data with real operational weight in somebody
        else's hands. The manager-gated route still exists, for the assistant
        who cannot or will not upload one.

        A photograph is uploaded as a **file**, never as a URL. Accepting a URL
        would let an assistant point their portrait at any address on the
        internet, which the map would then load on every pin.
    """
    hca_id = _own_hca_id(caller)
    payload = await photo.read()
    logger.info(
        "Assistant %s is replacing their own photograph (%d bytes).",
        hca_id,
        len(payload),
    )
    updated = await service.set_photo(hca_id, payload)
    return HcaResponse.from_hca(updated)


@router.delete("/hca/photo", response_model=HcaResponse)
async def remove_my_photo(
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> HcaResponse:
    """Remove the caller's own photograph.

    Args:
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Returns:
        HcaResponse: The updated record, with no photograph.

    Raises:
        MTHcaForbidden: If the account is bound to no assistant record;
            answered as a 403.

    Notes:
        The map falls back to the assistant's initials, so removing a portrait
        leaves a legible pin rather than a blank circle.
    """
    hca_id = _own_hca_id(caller)
    logger.info("Assistant %s is removing their own photograph.", hca_id)
    updated = await service.clear_photo(hca_id)
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


@router.put("/quotes/{quote_id}/lines", response_model=Quote)
async def replace_my_quote_lines(
    quote_id: str,
    quote: Quote,
    service: QuoteService = Depends(get_quote_service),
    caller: User = Depends(get_current_user),
) -> Quote:
    """Rewrite the services on one of the caller's own drafts, and reprice it.

    Args:
        quote_id (str): The quote to change.
        quote (Quote): A quote carrying the new lines.
        service (QuoteService): The quote service.
        caller (User): The authenticated caller.

    Returns:
        Quote: The repriced quote.

    Raises:
        MTQuoteNotFound: If no such quote exists; answered as a 404.
        MTQuoteForbidden: If the caller did not write it; answered as a 403.
        MTQuoteNotEditable: If it is past draft; answered as a 409.
        MTPricingUnknownInterventionType: If a line names a type that is not in
            the catalog; answered as a 422.

    Notes:
        - The assistant's half of the editing surface. A manager edits any quote
          in the agency through ``PUT /api/v1/quotes/{id}/lines``; this one is
          narrowed to the caller's own by the service, against the stored
          author rather than against anything in the payload.
        - **Only a draft may change**, for both roles. What a customer was sent
          has to be what the system holds — editing underneath them is how
          somebody accepts one thing and is billed for another — and a quote
          awaiting validation is frozen so a manager rules on the figures they
          were actually shown.
        - Only the lines are taken. The customer and the status stay as stored,
          so editing cannot reassign the quote or accept it on the customer's
          behalf.
    """
    logger.info("Assistant %s is editing quote %s.", caller.email, quote_id)
    return await service.replace_lines(
        quote_id, quote, author_id=caller.id or caller.email
    )


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
        caller.company_id,
        {
            "quote_id": submitted.id,
            "reference": submitted.reference,
            "author_id": caller.id,
            "author_name": caller.full_name,
            "company_id": caller.company_id,
        },
    )
    return submitted
