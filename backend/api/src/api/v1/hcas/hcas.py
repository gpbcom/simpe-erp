from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import get_hca_service, get_manager_user
from models.auth.user import User
from models.enums import ContractType
from models.people.hca import Hca
from models.schemas.requests.employment_update_request import EmploymentUpdateRequest
from models.schemas.responses.hca_response import HcaResponse
from service.hcas.hcas import HcaService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/hcas", tags=["Home care assistants"])


@router.post("", response_model=HcaResponse, status_code=status.HTTP_201_CREATED)
async def create_hca(
    hca: Hca,
    service: HcaService = Depends(get_hca_service),
    _: User = Depends(get_manager_user),
) -> HcaResponse:
    """Register a home care assistant.

    Args:
        hca (Hca): The assistant to register.
        service (HcaService): The assistant service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        HcaResponse: The stored assistant, with its identifier.

    Notes:
        The home address matters more here than anywhere else: it is where
        every round starts and ends, so an assistant whose address does not
        resolve is left out of the planning entirely.
    """
    logger.info("Creating an assistant.")
    return HcaResponse.from_hca(await service.create(hca))


@router.get("", response_model=List[HcaResponse])
async def list_hcas(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    search: Optional[str] = Query(default=None),
    contract_type: Optional[ContractType] = Query(default=None),
    service: HcaService = Depends(get_hca_service),
    _: User = Depends(get_manager_user),
) -> List[HcaResponse]:
    """List assistants.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        search (Optional[str]): Case-insensitive fragment of a name.
        contract_type (Optional[ContractType]): Restrict to one contract.
        service (HcaService): The assistant service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[HcaResponse]: The matching assistants.
    """
    logger.debug("Listing assistants: page=%d search=%r.", page, search)
    assistants = await service.list(
        page=page, size=size, search=search, contract_type=contract_type
    )
    return [HcaResponse.from_hca(assistant) for assistant in assistants]


@router.get("/{hca_id}", response_model=HcaResponse)
async def get_hca(
    hca_id: str,
    service: HcaService = Depends(get_hca_service),
    _: User = Depends(get_manager_user),
) -> HcaResponse:
    """Return one assistant.

    Args:
        hca_id (str): The assistant to read.
        service (HcaService): The assistant service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        HcaResponse: The assistant.

    Raises:
        MTHcaNotFound: If no such assistant exists; answered as a 404.
    """
    logger.debug("Reading assistant %s.", hca_id)
    return HcaResponse.from_hca(await service.get(hca_id))


@router.patch("/{hca_id}/employment", response_model=HcaResponse)
async def set_hca_employment(
    hca_id: str,
    payload: EmploymentUpdateRequest,
    service: HcaService = Depends(get_hca_service),
    _: User = Depends(get_manager_user),
) -> HcaResponse:
    """Change an assistant's contract type and qualifications.

    Args:
        hca_id (str): The assistant to change.
        payload (EmploymentUpdateRequest): The contract and certifications.
        service (HcaService): The assistant service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        HcaResponse: The updated assistant.

    Raises:
        MTHcaNotFound: If no such assistant exists; answered as a 404.

    Notes:
        **This is the only route by which a manager may edit an assistant, and
        the payload is the permission.** "A manager may change the contract
        type and the certifications" is enforced by
        :class:`EmploymentUpdateRequest` carrying exactly those two fields —
        there is no manager-reachable route accepting a whole assistant, so
        the contact details, the home address and the declared availability
        cannot be reached from a manager's session at all.
    """
    logger.info(
        "Setting assistant %s to a %s contract with %d certification(s).",
        hca_id,
        payload.contract_type.value,
        len(payload.certifications),
    )
    return HcaResponse.from_hca(
        await service.set_employment(
            hca_id, payload.contract_type, payload.certifications
        )
    )


@router.delete("/{hca_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hca(
    hca_id: str,
    service: HcaService = Depends(get_hca_service),
    _: User = Depends(get_manager_user),
) -> None:
    """Remove an assistant who has no account.

    Args:
        hca_id (str): The assistant to remove.
        service (HcaService): The assistant service.
        _ (User): The authenticated caller; enforces manager access.

    Raises:
        MTHcaNotFound: If no such assistant exists; answered as a 404.
        MTHcaHasAccount: If a login is still bound to them; answered as a 409.
    """
    logger.info("Deleting assistant %s.", hca_id)
    await service.delete(hca_id)
