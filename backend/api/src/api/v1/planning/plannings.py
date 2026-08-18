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
from models.planning.customer_planning import CustomerPlanning
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
        MTPlanningRunNotFound: If no planning covers the assistant. Answered
            as a 404.

    Notes:
        **The row-level check lives in the service, not in a guard here.** A
        guard can only establish that the caller is an assistant. It cannot
        stop assistant A putting assistant B's identifier in the path. The
        service compares the requested assistant against the caller's own
        record, which is the only place that comparison can be made.
    """
    return await service.planning(hca_id, caller, period_start, period_end)


@router.get("/customers", response_model=List[CustomerPlanning])
async def list_customer_plannings(
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: PlanningService = Depends(get_planning_service),
    caller: User = Depends(get_current_user),
) -> List[CustomerPlanning]:
    """Return the households' care the caller is allowed to see.

    Args:
        period_start (date): First day of interest, inclusive.
        period_end (date): Last day of interest, inclusive.
        service (PlanningService): The planning service.
        caller (User): The authenticated caller.

    Returns:
        List[CustomerPlanning]: Every household with care in the period for a
        manager or administrator; only the assistant's own portfolio for an
        assistant.

    Raises:
        MTPlanningForbidden: If a household reaches this route, or an assistant
            account names no assistant record. Answered as a 403.

    Notes:
        - **The same visits as ``/hcas``, grouped by the other party.** An
          intervention names both an assistant and a household, so the calendar
          groups two ways: who delivers the care, and who receives it. Neither
          is a filter over the other's answer.
        - **This is what a household reads at ``/api/v1/portal/planning``**,
          read through the same repository method with the same arguments. The
          agency and the family are looking at one query, not two that happen to
          agree.
        - The narrowing happens in the service. A route guard proves only that
          the caller is signed in. It cannot express "the households this
          assistant visits", which is a row-level question.
    """
    logger.debug(
        "Listing the customers planning for %s from %s to %s.",
        caller.email,
        period_start,
        period_end,
    )
    return await service.customer_plannings(caller, period_start, period_end)


@router.get("/customers/{customer_id}", response_model=CustomerPlanning)
async def get_customer_planning(
    customer_id: str,
    period_start: date = Query(...),
    period_end: date = Query(...),
    service: PlanningService = Depends(get_planning_service),
    caller: User = Depends(get_current_user),
) -> CustomerPlanning:
    """Return one household's care, if the caller may see it.

    Args:
        customer_id (str): The household whose care is wanted.
        period_start (date): First day of interest, inclusive.
        period_end (date): Last day of interest, inclusive.
        service (PlanningService): The planning service.
        caller (User): The authenticated caller.

    Returns:
        CustomerPlanning: The household's visits over the period.

    Raises:
        MTPlanningForbidden: If a household reaches this route. Answered as a
            403.
        MTPlanningCustomerNotFound: If the household does not exist or is not in
            the asking assistant's portfolio. Answered as a **404** either way.

    Notes:
        Declared **after** ``/customers`` so the literal path is matched first.
        FastAPI matches in declaration order, and a parametrised route declared
        ahead of its sibling swallows it — ``/customers`` would arrive here as a
        household named "customers".
    """
    logger.debug("Reading the care of household %s for %s.", customer_id, caller.email)
    return await service.planning_for_customer(
        customer_id, caller, period_start, period_end
    )
