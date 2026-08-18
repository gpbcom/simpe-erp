from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import (
    get_current_user,
    get_manager_user,
    get_skill_type_service,
)
from models.auth.user import User
from models.catalog.skill_type import SkillType
from models.schemas.requests.catalog.skill_type_filter import SkillTypeFilter
from models.schemas.requests.catalog.skill_type_update_request import (
    SkillTypeUpdateRequest,
)
from service.skills.skills import SkillTypeService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/skills", tags=["Skills"])


@router.get("", response_model=List[SkillType])
async def list_skill_types(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=500),
    include_inactive: bool = Query(default=False),
    skill_filter: SkillTypeFilter = Depends(),
    service: SkillTypeService = Depends(get_skill_type_service),
    _: User = Depends(get_current_user),
) -> List[SkillType]:
    """List the skills the agency recognises.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        include_inactive (bool): Whether retired entries are included.
        skill_filter (SkillTypeFilter): The filters, bound from the query string.
            Every field is optional and an absent one narrows nothing.
        service (SkillTypeService): The catalogue service.
        _ (User): The authenticated caller.

    Returns:
        List[SkillType]: The matching entries, ordered by label.

    Notes:
        **Readable by any signed-in caller, and that matters more here than for
        the certification catalogue.** An assistant declares their own skills
        from their own account screen, so this is the list they pick from —
        a screen that could not read it would leave them typing a code from
        memory and matching nothing.

        Retired entries are hidden unless asked for, so the picker offers only
        what may still be declared.
    """
    return await service.list(
        page=page,
        size=size,
        include_inactive=include_inactive,
        skill_filter=skill_filter,
    )


@router.post("", response_model=SkillType, status_code=status.HTTP_201_CREATED)
async def create_skill_type(
    skill_type: SkillType,
    service: SkillTypeService = Depends(get_skill_type_service),
    caller: User = Depends(get_manager_user),
) -> SkillType:
    """Add a skill to the catalogue.

    Args:
        skill_type (SkillType): The entry to add.
        service (SkillTypeService): The catalogue service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        SkillType: The stored entry.

    Raises:
        MTSkillTypeAlreadyExists: If the code is taken. Answered as a 409.

    Notes:
        **The catalogue is a manager's, even though the declarations are not.**
        An assistant says what they can do; what the agency is willing to
        recognise and plan against is the agency's decision, and a workforce
        able to invent catalogue entries would produce a list nobody could
        require anything from.
    """
    stored = await service.create(skill_type)
    logger.info("%s added skill %s to the catalogue.", caller.email, stored.code)
    return stored


@router.patch("/{type_id}", response_model=SkillType)
async def update_skill_type(
    type_id: str,
    payload: SkillTypeUpdateRequest,
    service: SkillTypeService = Depends(get_skill_type_service),
    caller: User = Depends(get_manager_user),
) -> SkillType:
    """Change what a catalogue entry says.

    Args:
        type_id (str): The entry to change.
        payload (SkillTypeUpdateRequest): What to change about it.
        service (SkillTypeService): The catalogue service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        SkillType: The updated entry.

    Raises:
        MTSkillTypeNotFound: If no such entry exists. Answered as a 404.

    Notes:
        ``PATCH`` and not ``PUT``, and the payload carries no ``code``. A code
        is what every declared skill and every service requirement is matched
        on, so renaming one would un-skill its holders on the next planning run
        — see
        :class:`~models.schemas.requests.catalog.skill_type_update_request.SkillTypeUpdateRequest`.
    """
    changes = payload.model_dump(exclude_unset=True)
    updated = await service.update(
        type_id,
        label=changes.get("label"),
        description=changes.get("description"),
        is_active=changes.get("is_active"),
    )
    logger.info(
        "%s changed skill %s: %s.",
        caller.email,
        updated.code,
        ", ".join(sorted(changes)) or "nothing",
    )
    return updated


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_type(
    type_id: str,
    service: SkillTypeService = Depends(get_skill_type_service),
    caller: User = Depends(get_manager_user),
) -> None:
    """Remove a catalogue entry that nothing refers to.

    Args:
        type_id (str): The entry to remove.
        service (SkillTypeService): The catalogue service.
        caller (User): The authenticated caller; enforces manager access.

    Raises:
        MTSkillTypeNotFound: If no such entry exists. Answered as a 404.
        MTSkillTypeInUse: If an assistant has declared it or a service requires
            it. Answered as a 409 naming both counts.

    Notes:
        **Retiring is the ordinary way to take a skill out of use.** This is for
        an entry added by mistake, which in practice means one added this
        morning. The refusal that follows a reference is not a formality — no
        foreign key protects those references, so a delete that went through
        would leave a requirement pointing at nothing, and a requirement
        pointing at nothing fails every planning run it touches.
    """
    logger.info("Deleting skill type %s at the request of %s.", type_id, caller.email)
    await service.delete(type_id)
