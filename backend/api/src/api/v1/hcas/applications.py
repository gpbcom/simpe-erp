from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Body, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_hca_application_service,
    get_manager_user,
)
from models.auth.user import User
from models.people.hca_application import HcaApplication
from models.schemas.requests.application_decision_request import (
    ApplicationDecisionRequest,
)
from models.schemas.requests.hca_application_request import HcaApplicationRequest
from service.hcas.hcas import HcaService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/hca-applications", tags=["HCA applications"])


@router.post("", response_model=HcaApplication, status_code=status.HTTP_201_CREATED)
async def submit_application(
    payload: HcaApplicationRequest,
    service: HcaService = Depends(get_hca_application_service),
) -> HcaApplication:
    """Apply to work for a company.

    Args:
        payload (HcaApplicationRequest): The applicant's details, chosen
            company and chosen password.
        service (HcaService): The assistant service.

    Returns:
        HcaApplication: The pending application.

    Raises:
        MTCompanyNotFound: If the chosen company does not exist; 404.
        MTCompanyNotAcceptingApplications: If it has closed its queue; 409.
        MTDuplicateApplication: If one is already pending; 409.

    Notes:
        **Public, and it has to be**: this is the route by which an assistant
        with no account asks for one, choosing which company to register with.

        It creates no account and grants nothing. Until somebody at the chosen
        company approves it, the applicant cannot sign in and does not appear
        in the users table — so an unvetted submission is a row in a queue, not
        a way in.

        The response deliberately does not echo the password back, and the
        model it is built from stores only its hash.
    """
    logger.info(
        "Receiving an application from %s to company %s.",
        payload.email,
        payload.company_id,
    )
    return await service.submit(
        company_id=payload.company_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone_number=str(payload.phone_number),
        email=str(payload.email),
        password=payload.password,
        address=payload.address,
        contract_type=payload.contract_type,
    )


@router.get("", response_model=List[HcaApplication])
async def list_applications(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    service: HcaService = Depends(get_hca_application_service),
    caller: User = Depends(get_manager_user),
) -> List[HcaApplication]:
    """Return the applications awaiting the caller's company.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        List[HcaApplication]: The pending applications, oldest first.

    Notes:
        There is no company parameter. The queue is chosen from the caller's
        own company, because a company identifier in the query string would let
        a manager read another agency's hiring queue by changing it.
    """
    logger.debug("Listing pending applications for %s.", caller.email)
    return await service.list_pending(caller, page=page, size=size)


@router.get("/{application_id}", response_model=HcaApplication)
async def get_application(
    application_id: str,
    service: HcaService = Depends(get_hca_application_service),
    caller: User = Depends(get_manager_user),
) -> HcaApplication:
    """Return one application.

    Args:
        application_id (str): The application to read.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        HcaApplication: The application.

    Raises:
        MTApplicationNotFound: If no such application exists; 404.
        MTApplicationForbidden: If it belongs to another company; 403.
    """
    logger.debug("Reading application %s.", application_id)
    return await service.get_application(application_id, caller)


@router.post("/{application_id}/approve", response_model=HcaApplication)
async def approve_application(
    application_id: str,
    payload: ApplicationDecisionRequest,
    service: HcaService = Depends(get_hca_application_service),
    caller: User = Depends(get_manager_user),
) -> HcaApplication:
    """Accept an application, creating the assistant and their account.

    Args:
        application_id (str): The application to approve.
        payload (ApplicationDecisionRequest): The contract they are taken on
            under.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the decider.

    Returns:
        HcaApplication: The approved application, naming the new assistant.

    Raises:
        MTApplicationNotFound: If no such application exists; 404.
        MTApplicationForbidden: If it belongs to another company; 403.
        MTApplicationAlreadyDecided: If it was already decided; 409.

    Notes:
        **This is the validation the specification requires** before a
        self-registered assistant is accepted. The account created here uses
        the password the applicant chose, so nothing has to be handed over and
        nothing has to be changed at first sign-in.
    """
    logger.info(
        "Approving application %s on a %s contract, decided by %s.",
        application_id,
        payload.contract_type.value,
        caller.email,
    )
    return await service.approve(application_id, caller, payload.contract_type)


@router.post("/{application_id}/reject", response_model=HcaApplication)
async def reject_application(
    application_id: str,
    reason: str = Body(default=None, embed=True),
    service: HcaService = Depends(get_hca_application_service),
    caller: User = Depends(get_manager_user),
) -> HcaApplication:
    """Decline an application, creating nothing.

    Args:
        application_id (str): The application to decline.
        reason (str): Why, for the record.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller; enforces manager access and is
            recorded as the decider.

    Returns:
        HcaApplication: The declined application.

    Raises:
        MTApplicationNotFound: If no such application exists; 404.
        MTApplicationForbidden: If it belongs to another company; 403.
        MTApplicationAlreadyDecided: If it was already decided; 409.
    """
    logger.info(
        "Declining application %s, decided by %s.", application_id, caller.email
    )
    return await service.reject(application_id, caller, reason)
