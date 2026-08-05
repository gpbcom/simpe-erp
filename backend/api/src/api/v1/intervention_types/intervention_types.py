from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import get_intervention_type_service, get_manager_user
from models.auth.user import User
from models.catalog.intervention_type import InterventionType
from service.intervention_types.intervention_types import (
    InterventionTypeService,  # noqa: E501
)

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/intervention-types", tags=["Intervention types"])


@router.post("", response_model=InterventionType, status_code=status.HTTP_201_CREATED)
async def create_intervention_type(
    intervention_type: InterventionType,
    service: InterventionTypeService = Depends(get_intervention_type_service),
    _: User = Depends(get_manager_user),
) -> InterventionType:
    """Add a service to the catalog.

    Args:
        intervention_type (InterventionType): The type to add.
        service (InterventionTypeService): The catalog service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        InterventionType: The stored type.

    Raises:
        MTInterventionTypeAlreadyExists: If the name or code is taken;
            answered as a 409.
    """
    return await service.create(intervention_type)


@router.get("", response_model=List[InterventionType])
async def list_intervention_types(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    include_inactive: bool = Query(default=False),
    service: InterventionTypeService = Depends(get_intervention_type_service),
    _: User = Depends(get_manager_user),
) -> List[InterventionType]:
    """List the catalog.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        include_inactive (bool): Whether retired types are included.
        service (InterventionTypeService): The catalog service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        List[InterventionType]: The matching types.

    Notes:
        Retired types are hidden unless asked for, so a quote-building screen
        offers only what may still be sold.
    """
    return await service.list(page=page, size=size, include_inactive=include_inactive)


@router.get("/{type_id}", response_model=InterventionType)
async def get_intervention_type(
    type_id: str,
    service: InterventionTypeService = Depends(get_intervention_type_service),
    _: User = Depends(get_manager_user),
) -> InterventionType:
    """Return one service from the catalog.

    Args:
        type_id (str): The type to read.
        service (InterventionTypeService): The catalog service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        InterventionType: The type.

    Raises:
        MTInterventionTypeNotFound: If no such type exists; answered as a 404.
    """
    return await service.get(type_id)


@router.patch("/{type_id}", response_model=InterventionType)
async def update_intervention_type(
    type_id: str,
    intervention_type: InterventionType,
    service: InterventionTypeService = Depends(get_intervention_type_service),
    _: User = Depends(get_manager_user),
) -> InterventionType:
    """Update a service in the catalog.

    Args:
        type_id (str): The type to update.
        intervention_type (InterventionType): The new values.
        service (InterventionTypeService): The catalog service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        InterventionType: The updated type.

    Raises:
        MTInterventionTypeNotFound: If no such type exists; answered as a 404.
        MTInterventionTypeAlreadyExists: If the new name or code is taken;
            answered as a 409.

    Notes:
        The identifier comes from the path, never from the body. Taking it from
        the payload would let a caller update a different type than the one
        their URL names.
    """
    return await service.update(intervention_type.model_copy(update={"id": type_id}))


@router.delete("/{type_id}", response_model=InterventionType)
async def retire_intervention_type(
    type_id: str,
    service: InterventionTypeService = Depends(get_intervention_type_service),
    _: User = Depends(get_manager_user),
) -> InterventionType:
    """Take a service out of the sellable catalog.

    Args:
        type_id (str): The type to retire.
        service (InterventionTypeService): The catalog service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        InterventionType: The retired type.

    Raises:
        MTInterventionTypeNotFound: If no such type exists; answered as a 404.

    Notes:
        A soft delete, despite the verb. The row stays so a quote issued last
        year can still be printed and its VAT rate still explained; the type
        simply stops appearing when a new quote is built.
    """
    return await service.retire(type_id)
