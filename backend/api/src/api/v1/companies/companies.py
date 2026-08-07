from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_admin_user,
    get_company_registration_service,
    get_company_service,
    get_manager_user,
)
from models.auth.user import User
from models.companies.company import Company
from models.companies.company_choice import CompanyChoice
from models.schemas.requests.companies.company_registration_request import (
    CompanyRegistrationRequest,
)
from models.schemas.responses.companies.company_registration_response import (
    CompanyRegistrationResponse,
)
from models.schemas.responses.auth.user_response import UserResponse
from service.companies.companies import CompanyService
from service.companies.registration import CompanyRegistrationService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/companies", tags=["Companies"])


@router.post(
    "/registration",
    response_model=CompanyRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_company(
    payload: CompanyRegistrationRequest,
    service: CompanyRegistrationService = Depends(get_company_registration_service),
) -> CompanyRegistrationResponse:
    """Found an agency and become its administrator.

    Args:
        payload (CompanyRegistrationRequest): The agency and its founder.
        service (CompanyRegistrationService): The registration service.

    Returns:
        CompanyRegistrationResponse: The new agency and its administrator.

    Raises:
        MTCompanyRegistrationDisabled: If the deployment has not opted in;
            answered as a 404, so it looks like no such route.
        MTCompanyNameTaken: If another agency trades under the name; 409.
        MTAuthEmailAlreadyRegistered: If the address is taken; 409.

    Notes:
        - **Unauthenticated, and the only route that grants an administrator
          role without one.** That is safe only because the administrator's
          rights are over an agency created by this same call: there is no
          field naming an existing company, so there is nothing to take over.
          The sibling route ``POST /api/v1/auth/register`` is unauthenticated
          too and always yields an assistant, for the same reason turned the
          other way — it attaches to records that already exist.
        - **Off unless the deployment opts in**, because a company is not yet a
          tenancy boundary: an administrator minted here can read every
          agency's customers, quotes and plannings, not only their own. See
          :attr:`~models.configuration.auth_config.AuthConfig.allow_company_registration`.
        - No token comes back. The founder signs in through the ordinary login
          route with the password they just chose, so there is one place that
          mints credentials rather than two.
    """
    logger.info("Founding agency %r for %s.", payload.company_name, payload.email)
    company, administrator = await service.register(
        company_name=payload.company_name,
        registration_number=payload.registration_number,
        full_name=payload.full_name,
        email=str(payload.email),
        password=payload.password,
    )
    return CompanyRegistrationResponse(
        company=company,
        administrator=UserResponse.from_user(administrator),
    )


@router.get("/choices", response_model=List[CompanyChoice])
async def list_company_choices(
    service: CompanyService = Depends(get_company_service),
) -> List[CompanyChoice]:
    """Return the companies an applicant may choose between.

    Args:
        service (CompanyService): The company service.

    Returns:
        List[CompanyChoice]: Identifier and name only, for those accepting
        applications.

    Notes:
        **Public: no credential, and none possible.** An assistant applying for
        work does not have an account yet, and cannot choose a company without
        seeing the list.

        What that costs is bounded by the response model: a
        :class:`~models.companies.company_choice.CompanyChoice` carries an
        identifier and a name, so this cannot become a directory of every
        agency's registered office however the service changes.
    """
    logger.debug("Serving the public company list.")
    return await service.choices()


@router.post("", response_model=Company, status_code=status.HTTP_201_CREATED)
async def create_company(
    company: Company,
    service: CompanyService = Depends(get_company_service),
    _: User = Depends(get_admin_user),
) -> Company:
    """Register a company.

    Args:
        company (Company): The company to register.
        service (CompanyService): The company service.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        Company: The stored company.

    Raises:
        MTCompanyNameTaken: If the name is already in use; answered as a 409.

    Notes:
        Administrator-only. A company is who an applicant ends up working for,
        and a manager able to create one could create a destination for
        applications nobody oversees.
    """
    logger.info("Creating company %s.", company.name)
    return await service.create(company)


@router.get("", response_model=List[Company])
async def list_companies(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    service: CompanyService = Depends(get_company_service),
    _: User = Depends(get_manager_user),
) -> List[Company]:
    """List companies in full.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        service (CompanyService): The company service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[Company]: The companies, contact details included.
    """
    logger.debug("Listing companies: page=%d.", page)
    return await service.list(page=page, size=size)


@router.get("/{company_id}", response_model=Company)
async def get_company(
    company_id: str,
    service: CompanyService = Depends(get_company_service),
    _: User = Depends(get_manager_user),
) -> Company:
    """Return one company.

    Args:
        company_id (str): The company to read.
        service (CompanyService): The company service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        Company: The company.

    Raises:
        MTCompanyNotFound: If no such company exists; answered as a 404.
    """
    logger.debug("Reading company %s.", company_id)
    return await service.get(company_id)


@router.put("/{company_id}", response_model=Company)
async def update_company(
    company_id: str,
    company: Company,
    service: CompanyService = Depends(get_company_service),
    _: User = Depends(get_admin_user),
) -> Company:
    """Replace a company's details.

    Args:
        company_id (str): The company to change.
        company (Company): The new details.
        service (CompanyService): The company service.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        Company: The updated company.

    Raises:
        MTCompanyNotFound: If no such company exists; answered as a 404.
    """
    logger.info("Updating company %s.", company_id)
    return await service.update(company_id, company)


@router.patch("/{company_id}/applications", response_model=Company)
async def set_company_applications(
    company_id: str,
    is_accepting: bool = Query(...),
    service: CompanyService = Depends(get_company_service),
    _: User = Depends(get_admin_user),
) -> Company:
    """Open or close a company to new applications.

    Args:
        company_id (str): The company to change.
        is_accepting (bool): Whether it appears on the public list.
        service (CompanyService): The company service.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        Company: The updated company.

    Raises:
        MTCompanyNotFound: If no such company exists; answered as a 404.

    Notes:
        Closing hides the company from applicants; it does not touch the
        applications already waiting. Somebody who applied yesterday still
        deserves a decision.
    """
    logger.info(
        "Setting company %s to %s applications.",
        company_id,
        "accept" if is_accepting else "refuse",
    )
    return await service.set_accepting_applications(company_id, is_accepting)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: str,
    service: CompanyService = Depends(get_company_service),
    caller: User = Depends(get_admin_user),
) -> None:
    """Remove an agency that nobody belongs to.

    Args:
        company_id (str): The agency to remove.
        service (CompanyService): The company service.
        caller (User): The authenticated caller; enforces administrator access.

    Raises:
        MTCompanyNotFound: If no such agency exists; answered as a 404.
        MTCompanyNotEmpty: If an account or an assistant still names it;
            answered as a 409.

    Notes:
        - Administrator-gated, and only while the agency is empty. Every
          account and every assistant names the agency they belong to, so
          removing one underneath them would leave rows nothing can rebuild.
        - An agency that has people is **closed to applications**, not deleted.
          This exists for the one founded in error, and for the fixtures a test
          campaign is obliged to remove after itself.
    """
    logger.info("Deleting agency %s at the request of %s.", company_id, caller.email)
    await service.delete(company_id)
