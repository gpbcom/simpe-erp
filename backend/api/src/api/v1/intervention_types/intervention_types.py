from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_app_config,
    get_intervention_type_service,
    get_manager_user,
)
from models.auth.user import User
from models.catalog.intervention_type import InterventionType
from models.configuration.app_config import AppConfig
from models.schemas.requests.intervention_type_update_request import (
    InterventionTypeUpdateRequest,
)
from models.schemas.responses.pricing_rules_response import PricingRulesResponse
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


@router.get("/pricing-rules", response_model=PricingRulesResponse)
async def read_pricing_rules(
    config: AppConfig = Depends(get_app_config),
    _: User = Depends(get_manager_user),
) -> PricingRulesResponse:
    """Return the agency-wide rules a catalogue entry is priced against.

    Args:
        config (AppConfig): The running configuration.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        PricingRulesResponse: The default rate, the surcharges and the VAT
        rates each service category carries.

    Notes:
        **Declared before ``/{type_id}``.** Routes are matched in the order they
        are registered, so with the parameterised route first this path would
        be read as a request for the intervention type whose identifier is
        ``"pricing-rules"`` — a 404 that names a type nobody asked for.

        Read-only. These rules live in configuration rather than the database:
        a rate change is a commercial decision with a deployment behind it, not
        a form. What a *type* charges is editable, and that is the next route
        down.
    """
    logger.debug("Publishing the agency-wide pricing rules.")
    return PricingRulesResponse.from_config(config.pricing)


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
    request: InterventionTypeUpdateRequest,
    service: InterventionTypeService = Depends(get_intervention_type_service),
    _: User = Depends(get_manager_user),
) -> InterventionType:
    """Change part of a service in the catalog.

    Args:
        type_id (str): The type to update.
        request (InterventionTypeUpdateRequest): The fields to change.
        service (InterventionTypeService): The catalog service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        InterventionType: The updated type.

    Raises:
        MTInterventionTypeNotFound: If no such type exists; answered as a 404.
        MTInterventionTypeAlreadyExists: If the new name is taken; answered as
            a 409.

    Notes:
        **A partial payload, as the verb has always claimed.** This route was
        declared ``PATCH`` but took a whole ``InterventionType``, so changing a
        rate meant resending the name, the code, the category and the active
        flag — and a client that sent only what it had changed was answered
        ``422: code Field required``.

        ``exclude_unset=True`` is what separates "leave the rate alone" from
        "clear the rate so this entry bills at the agency rate". Both arrive as
        an absent value on an optional field; only the set of keys the caller
        actually sent tells them apart, and a merge that ignored it would reset
        an entry's rate every time somebody corrected its spelling.

        The identifier comes from the path, never the body, and ``code`` is not
        on the payload at all — see
        :class:`~models.schemas.requests.intervention_type_update_request.InterventionTypeUpdateRequest`.
    """
    existing = await service.get(type_id)
    changes = request.model_dump(exclude_unset=True)
    logger.info("Updating catalogue entry %s: %s.", type_id, sorted(changes))
    return await service.update(existing.model_copy(update={**changes, "id": type_id}))


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
