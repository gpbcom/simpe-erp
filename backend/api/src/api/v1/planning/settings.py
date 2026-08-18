from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends

# First-party imports
from api.dependencies import get_manager_user, get_planning_service  # noqa: E501
from models.auth.user import User
from models.schemas.requests.planning.planning_settings_request import (
    PlanningSettingsRequest,  # noqa: E501
)
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
        payload (PlanningSettingsRequest): The new radius, working day and
            lunch rules.
        service (PlanningService): The planning service, which owns the
            manager-editable rules.
        caller (User): The authenticated caller; enforces manager access and is
            recorded against the change.

    Returns:
        PlanningSettings: The rules now in force.

    Raises:
        MTPlanningSettingsRequestInvalidRadius: When the radius is outside the
            accepted range. Answered as a 422.
        MTPlanningSettingsRequestInvalidDayEnd: When the working day ends at or
            before it starts. Answered as a 422.
        MTPlanningSettingsRequestInvalidLunchWindow: When the lunch window
            falls outside the working day or is too narrow to hold the break;
            answered as a 422.

    Notes:
        - Manager-gated, matching the specification's "the admin and/or manager
          will define them". An administrator passes the same guard, since the
          role ranks above a manager.
        - **The working day and the lunch window arrive here rather than from
          ``app.yaml``.** They are the same kind of decision as the radius, and
          keeping them in the configuration file made "we open at 08:00 now" a
          deployment.
        - **A change does not re-plan anything.** It applies to the next planning
          run. Silently recomputing this week because somebody adjusted a radius
          would move assistants who have already been told where to go.
    """
    logger.info(
        "Changing the planning settings to a %.1f km radius, a %d-%d minute "
        "working day and a %d minute lunch break, at the request of %s.",
        payload.max_intervention_radius_km,
        payload.day_start_minute,
        payload.day_end_minute,
        payload.lunch_break_minutes,
        caller.email,
    )
    return await service.update_settings(
        max_intervention_radius_km=payload.max_intervention_radius_km,
        day_start_minute=payload.day_start_minute,
        day_end_minute=payload.day_end_minute,
        lunch_break_minutes=payload.lunch_break_minutes,
        lunch_window_start_minute=payload.lunch_window_start_minute,
        lunch_window_end_minute=payload.lunch_window_end_minute,
        updated_by=caller.id if caller.id else caller.email,
    )
