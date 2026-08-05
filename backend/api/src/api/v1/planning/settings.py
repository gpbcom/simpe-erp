from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends

# First-party imports
from api.dependencies import get_manager_user, get_planning_service
from models.auth.user import User
from models.schemas.requests.planning_settings_request import PlanningSettingsRequest
from models.settings.planning_settings import PlanningSettings
from service.planning.plannings import PlanningService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/planning", tags=["Planning settings"])


@router.get("/settings", response_model=PlanningSettings)
async def get_planning_settings(
    service: PlanningService = Depends(get_planning_service),
    _: User = Depends(get_manager_user),
) -> PlanningSettings:
    """Return the planning rules in force.

    Args:
        service (PlanningService): The planning service, which owns the
            manager-editable rules.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        PlanningSettings: The rules, seeded from configuration on first read.
    """
    logger.debug("Reading the planning settings.")
    return await service.current_settings()


@router.put("/settings", response_model=PlanningSettings)
async def update_planning_settings(
    payload: PlanningSettingsRequest,
    service: PlanningService = Depends(get_planning_service),
    caller: User = Depends(get_manager_user),
) -> PlanningSettings:
    """Change the planning rules.

    Args:
        payload (PlanningSettingsRequest): The new radius and break length.
        service (PlanningService): The planning service, which owns the
            manager-editable rules.
        caller (User): The authenticated caller; enforces manager access and is
            recorded against the change.

    Returns:
        PlanningSettings: The rules now in force.

    Raises:
        MTPlanningSettingsRequestInvalidRadius: When the radius is outside the
            accepted range; answered as a 422.

    Notes:
        Manager-gated, matching the specification's "the admin and/or manager
        will define them". An administrator passes the same guard, since the
        role ranks above a manager.

        **A change does not re-plan anything.** It applies to the next planning
        run. Silently recomputing this week because somebody adjusted a radius
        would move assistants who have already been told where to go.
    """
    logger.info(
        "Changing the planning settings to a %.1f km radius and a %d minute "
        "lunch break, at the request of %s.",
        payload.max_intervention_radius_km,
        payload.lunch_break_minutes,
        caller.email,
    )
    return await service.update_settings(
        max_intervention_radius_km=payload.max_intervention_radius_km,
        lunch_break_minutes=payload.lunch_break_minutes,
        updated_by=caller.id if caller.id else caller.email,
    )
