from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query

# First-party imports
from api.dependencies import get_current_user, get_planning_service
from models.auth.user import User
from models.planning.hca_planning import HcaPlanning
from service.planning.plannings import PlanningService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/planning", tags=["Plannings"])


@router.get("/hcas", response_model=List[HcaPlanning])
async def list_plannings(
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: PlanningService = Depends(get_planning_service),
    caller: User = Depends(get_current_user),
) -> List[HcaPlanning]:
    """Return the diaries the caller is allowed to see.

    Args:
        period_start (date): First day of interest, inclusive.
        period_end (date): Last day of interest, inclusive.
        service (PlanningService): The planning service.
        caller (User): The authenticated caller.

    Returns:
        List[HcaPlanning]: Every diary for a manager or administrator; only
        their own for an assistant.

    Raises:
        MTPlanningForbidden: If an assistant account has no assistant record;
            answered as a 403.

    Notes:
        The narrowing happens in the service, not here. An assistant asking for
        "all plannings" gets a one-element list containing their own rather
        than a refusal — it is the same screen, and refusing would be
        gratuitous — but they can never receive somebody else's.
    """
    return await service.all_plannings(caller, period_start, period_end)


@router.get("/hcas/{hca_id}", response_model=HcaPlanning)
async def get_planning(
    hca_id: str,
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: PlanningService = Depends(get_planning_service),
    caller: User = Depends(get_current_user),
) -> HcaPlanning:
    """Return one assistant's diary.

    Args:
        hca_id (str): The assistant whose diary is wanted.
        period_start (date): First day of interest, inclusive.
        period_end (date): Last day of interest, inclusive.
        service (PlanningService): The planning service.
        caller (User): The authenticated caller.

    Returns:
        HcaPlanning: The diary.

    Raises:
        MTPlanningForbidden: If an assistant asks for somebody else's diary;
            answered as a 403.
        MTPlanningRunNotFound: If no planning covers the assistant; answered
            as a 404.

    Notes:
        **The row-level check lives in the service, not in a guard here.** A
        guard can only establish that the caller is an assistant; it cannot
        stop assistant A putting assistant B's identifier in the path. The
        service compares the requested assistant against the caller's own
        record, which is the only place that comparison can be made.
    """
    return await service.planning_for(hca_id, caller, period_start, period_end)
