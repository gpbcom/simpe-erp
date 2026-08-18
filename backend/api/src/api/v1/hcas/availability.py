from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import get_current_user, get_hca_service
from models.auth.user import User
from models.people.hca.availability_slot import AvailabilitySlot
from models.schemas.requests.hca.working_days_request import WorkingDaysRequest
from models.schemas.responses.hca.hca_response import HcaResponse
from service.hcas.hcas import HcaService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/hcas", tags=["Availability"])


@router.get("/{hca_id}/availability", response_model=List[AvailabilitySlot])
async def list_availability(
    hca_id: str,
    start: Optional[date] = Query(default=None),
    end: Optional[date] = Query(default=None),
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> List[AvailabilitySlot]:
    """Return an assistant's declared absences.

    Args:
        hca_id (str): The assistant to read.
        start (Optional[date]): Earliest day of interest.
        end (Optional[date]): Latest day of interest.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Returns:
        List[AvailabilitySlot]: The matching absences.

    Raises:
        MTHcaForbidden: If an assistant reads a colleague's absences. Answered
            as a 403.

    Notes:
        Gated on the caller being authenticated, not on a role — an assistant
        must be able to read their own. The narrowing is the service's, because
        only it can compare the addressed assistant against the caller's own
        record.
    """
    logger.debug("Listing absences for assistant %s.", hca_id)
    return await service.list_availability(hca_id, caller, start=start, end=end)


@router.put("/{hca_id}/working-days", response_model=HcaResponse)
async def set_working_days(
    hca_id: str,
    payload: WorkingDaysRequest,
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> HcaResponse:
    """Declare which days of the week an assistant works.

    Args:
        hca_id (str): The assistant whose working week is being set.
        payload (WorkingDaysRequest): The days now worked.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Returns:
        HcaResponse: The assistant, carrying their new working week.

    Raises:
        MTWorkingDaysRequestInvalidWeekdays: If the payload names no day or an
            unknown one. Answered as a 422.
        MTHcaForbidden: If an assistant sets a colleague's working week;
            answered as a 403.
        MTHcaNotFound: If no such assistant exists. Answered as a 404.

    Notes:
        Authenticated rather than role-gated, matching the absence routes: an
        assistant sets their own working week, and a manager or administrator
        sets anybody's. Which of the two the caller is can only be decided by
        the service, because only it can compare the addressed assistant
        against the caller's own record.

        The whole assistant comes back rather than just the week, so a client
        that has just changed it does not need a second call to redisplay the
        record — and so the working week and the absences are read from one
        shape in both directions.
    """
    logger.info(
        "Setting the working week of assistant %s to %s.",
        hca_id,
        ", ".join(day.value for day in payload.working_weekdays),
    )
    updated = await service.set_working_days(hca_id, payload.working_weekdays, caller)
    return HcaResponse.from_hca(updated)


@router.post(
    "/{hca_id}/availability",
    response_model=AvailabilitySlot,
    status_code=status.HTTP_201_CREATED,
)
async def add_availability(
    hca_id: str,
    slot: AvailabilitySlot,
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> AvailabilitySlot:
    """File an absence for an assistant.

    Args:
        hca_id (str): The assistant the absence belongs to.
        slot (AvailabilitySlot): The absence to record.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Returns:
        AvailabilitySlot: The stored absence.

    Raises:
        MTHcaForbidden: If an assistant files against a colleague. Answered as
            a 403.
        MTHcaNotFound: If no such assistant exists. Answered as a 404.

    Notes:
        This is the route by which an assistant declares their own
        availability. The owning assistant is taken from the path, never from
        the payload, so a body naming a colleague files against the addressed
        assistant — and the service refuses if that is not the caller.
    """
    logger.info(
        "Filing a %s absence for assistant %s from %s to %s.",
        slot.kind.value,
        hca_id,
        slot.start_date,
        slot.end_date,
    )
    return await service.add_availability(hca_id, slot, caller)


@router.delete(
    "/{hca_id}/availability/{slot_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_availability(
    hca_id: str,
    slot_id: str,
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_current_user),
) -> None:
    """Withdraw a filed absence.

    Args:
        hca_id (str): The assistant the absence belongs to.
        slot_id (str): The absence to withdraw.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller.

    Raises:
        MTHcaForbidden: If an assistant withdraws a colleague's absence;
            answered as a 403.
        MTAvailabilitySlotNotFound: If the absence does not belong to that
            assistant. Answered as a 404.

    Notes:
        Withdrawing an absence does not re-plan the period. The planning is
        recomputed on demand by an administrator, so a withdrawal makes the
        assistant available for the *next* run, not this week's calendar.
    """
    logger.info("Withdrawing absence %s for assistant %s.", slot_id, hca_id)
    await service.remove_availability(hca_id, slot_id, caller)
