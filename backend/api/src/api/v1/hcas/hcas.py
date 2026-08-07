from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Query, Response, status

# First-party imports
from api.dependencies import (
    get_event_publisher,
    get_hca_service,
    get_manager_user,
    get_planning_service,
)
from models.auth.user import User
from models.enums import ContractType
from models.people.hca import Hca
from models.planning.planning_run import PlanningRun
from models.schemas.requests.hca.employment_update_request import EmploymentUpdateRequest
from models.schemas.responses.hca.hca_response import HcaResponse
from service.hcas.hcas import HcaService
from service.messaging.publisher import EventPublisher
from service.planning.plannings import PlanningService

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
    caller: User = Depends(get_manager_user),
) -> HcaResponse:
    """Change an assistant's contract type, qualifications and rounds flag.

    Args:
        hca_id (str): The assistant to change.
        payload (EmploymentUpdateRequest): The contract, the certifications
            and whether the person goes out on rounds.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        HcaResponse: The updated assistant.

    Raises:
        MTHcaNotFound: If no such assistant exists; answered as a 404.

    Notes:
        - **This is the only route by which a manager may edit an assistant,
          and the payload is the permission.** "A manager may change the
          contract type, the certifications and whether this person goes out"
          is enforced by :class:`EmploymentUpdateRequest` carrying exactly
          those three fields — there is no manager-reachable route accepting a
          whole assistant, so the contact details, the home address and the
          declared availability cannot be reached from a manager's session at
          all.
        - **It addresses any record, including the caller's own.** The path
          takes an identifier and the guard asks only for the role, so a
          manager who also covers rounds sets their own flag through exactly
          the check they pass for anybody else. There is deliberately no
          separate self-service route: a second one would be a second place
          for the rule to drift.
        - ``field_employee`` was carried by the payload and dropped here for
          as long as the field has existed — the call took three arguments and
          the repository's default put the value back to ``True``. The switch
          on both screens has therefore never done anything, and an unrelated
          contract edit silently returned anybody who had been taken off the
          rounds. Nothing surfaced it: the request answers 200 with the
          unchanged record, which is indistinguishable from a no-op save.
    """
    logger.info(
        "Setting assistant %s to a %s contract with %d certification(s), "
        "field_employee=%s, at the request of %s.",
        hca_id,
        payload.contract_type.value,
        len(payload.certifications),
        payload.field_employee,
        caller.email,
    )
    return HcaResponse.from_hca(
        await service.set_employment(
            hca_id,
            payload.contract_type,
            payload.certifications,
            payload.field_employee,
        )
    )


@router.delete(
    "/{hca_id}",
    response_model=Optional[PlanningRun],
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_hca(
    hca_id: str,
    response: Response,
    service: HcaService = Depends(get_hca_service),
    plannings: PlanningService = Depends(get_planning_service),
    publisher: EventPublisher = Depends(get_event_publisher),
    caller: User = Depends(get_manager_user),
) -> Optional[PlanningRun]:
    """Remove an assistant, their account, and replan what they were due.

    Args:
        hca_id (str): The assistant to remove.
        response (Response): The response being built, so the status can drop
            to 204 when there is nothing to replan.
        service (HcaService): The assistant service.
        plannings (PlanningService): Records the replan.
        publisher (EventPublisher): Queues the solve for a worker.
        caller (User): The authenticated caller; enforces manager access and
            authorises removing the bound account.

    Returns:
        Optional[PlanningRun]: The pending replan with the identifier to poll,
        or ``None`` when the assistant had no future visits.

    Raises:
        MTHcaNotFound: If no such assistant exists; answered as a 404.
        MTHcaHasAccount: If a login is bound to them and cannot be removed;
            answered as a 409.
        MTAuthLastAdmin: If the bound account is the caller's own or the last
            administrator's; answered as a 409.

    Notes:
        - **The period is worked out here, not asked for.** A deletion from the
          workforce grid has no calendar window to take one from, and the days
          that actually need replanning are exactly the ones this person was
          due to work — see
          :meth:`~storage.repositories.planning.intervention.InterventionRepository.future_period_for_hca`.
        - **The period is measured before the delete**, because their visits go
          with them: asking afterwards would find nothing and replan nothing,
          leaving the rest of the workforce with a calendar built around
          somebody who has gone.
        - Answers **202** when a replan follows and **204** when none does.
          Queueing a run that would place the same visits in the same slots
          costs thirty seconds of a worker and makes the calendar flicker for
          no reason, so an assistant with no future work is simply removed.
    """
    period = await plannings.future_period_for_hca(hca_id)
    await service.delete(hca_id, requested_by=caller)
    logger.info("%s deleted assistant %s.", caller.email, hca_id)
    if period is None:
        logger.info("Assistant %s had no future visit; no replan is queued.", hca_id)
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return await plannings.queue_replan(
        requested_by=caller.id or caller.email,
        company_id=caller.company_id,
        period=period,
        publisher=publisher,
        reason=f"assistant {hca_id} was removed",
    )
