from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_certification_type_service,
    get_current_user,
    get_manager_user,
)
from models.auth.user import User
from models.catalog.certification_type import CertificationType
from models.schemas.requests.catalog.certification_type_filter import (
    CertificationTypeFilter,
)
from models.schemas.requests.catalog.certification_type_update_request import (
    CertificationTypeUpdateRequest,
)
from service.certifications.certifications import CertificationTypeService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/certifications", tags=["Certifications"])


@router.get("", response_model=List[CertificationType])
async def list_certification_types(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=500),
    include_inactive: bool = Query(default=False),
    certification_filter: CertificationTypeFilter = Depends(),
    service: CertificationTypeService = Depends(get_certification_type_service),
    _: User = Depends(get_current_user),
) -> List[CertificationType]:
    """List the qualifications the agency recognises.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        include_inactive (bool): Whether retired entries are included.
        certification_filter (CertificationTypeFilter): The filters, bound from the query string.
            Every field is optional and an absent one narrows nothing.
        service (CertificationTypeService): The catalogue service.
        _ (User): The authenticated caller.

    Returns:
        List[CertificationType]: The matching entries, ordered by label.

    Notes:
        **Readable by any signed-in caller**, unlike the writes below. An
        assistant's own account screen shows the qualifications they hold, and
        it names them by their catalogue label rather than by their code — a
        screen that could not read this would have to print ``DEAES`` at
        somebody and hope.

        Retired entries are hidden unless asked for, so a screen offering a
        requirement offers only what may still be required.
    """
    return await service.list(
        page=page,
        size=size,
        include_inactive=include_inactive,
        certification_filter=certification_filter,
    )


@router.post("", response_model=CertificationType, status_code=status.HTTP_201_CREATED)
async def create_certification_type(
    certification_type: CertificationType,
    service: CertificationTypeService = Depends(get_certification_type_service),
    caller: User = Depends(get_manager_user),
) -> CertificationType:
    """Add a qualification to the catalogue.

    Args:
        certification_type (CertificationType): The entry to add.
        service (CertificationTypeService): The catalogue service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        CertificationType: The stored entry.

    Raises:
        MTCertificationTypeAlreadyExists: If the code is taken; answered as a
            409.
    """
    stored = await service.create(certification_type)
    logger.info(
        "%s added certification %s to the catalogue.", caller.email, stored.code
    )
    return stored


@router.patch("/{type_id}", response_model=CertificationType)
async def update_certification_type(
    type_id: str,
    payload: CertificationTypeUpdateRequest,
    service: CertificationTypeService = Depends(get_certification_type_service),
    caller: User = Depends(get_manager_user),
) -> CertificationType:
    """Change what a catalogue entry says.

    Args:
        type_id (str): The entry to change.
        payload (CertificationTypeUpdateRequest): What to change about it.
        service (CertificationTypeService): The catalogue service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        CertificationType: The updated entry.

    Raises:
        MTCertificationTypeNotFound: If no such entry exists; answered as a
            404.

    Notes:
        ``PATCH`` and not ``PUT``, and the payload carries no ``code``. A code
        is what every stored qualification and every service requirement is
        matched on, so renaming one would disqualify its holders on the next
        planning run — see
        :class:`~models.schemas.requests.catalog.certification_type_update_request.CertificationTypeUpdateRequest`.
    """
    changes = payload.model_dump(exclude_unset=True)
    updated = await service.update(
        type_id,
        label=changes.get("label"),
        description=changes.get("description"),
        is_active=changes.get("is_active"),
    )
    logger.info(
        "%s changed certification %s: %s.",
        caller.email,
        updated.code,
        ", ".join(sorted(changes)) or "nothing",
    )
    return updated


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification_type(
    type_id: str,
    service: CertificationTypeService = Depends(get_certification_type_service),
    caller: User = Depends(get_manager_user),
) -> None:
    """Remove a catalogue entry that nothing refers to.

    Args:
        type_id (str): The entry to remove.
        service (CertificationTypeService): The catalogue service.
        caller (User): The authenticated caller; enforces manager access.

    Raises:
        MTCertificationTypeNotFound: If no such entry exists; answered as a
            404.
        MTCertificationTypeInUse: If an assistant holds it or a service
            requires it; answered as a 409 naming both counts.

    Notes:
        **Retiring is the ordinary way to take a qualification out of use.**
        This is for an entry added by mistake, which in practice means one
        added this morning. The refusal that follows a reference is not a
        formality — no foreign key protects those references, so a delete that
        went through would leave a requirement pointing at nothing, and a
        requirement pointing at nothing fails every planning run it touches.
    """
    logger.info(
        "Deleting certification type %s at the request of %s.", type_id, caller.email
    )
    await service.delete(type_id)
