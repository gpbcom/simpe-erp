from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends, status

# First-party imports
from api.dependencies import get_hca_service, get_manager_user
from models.auth.user import User
from service.hcas.hcas import HcaService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/hcas", tags=["Skills"])


@router.delete("/{hca_id}/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_skill(
    hca_id: str,
    skill_id: str,
    service: HcaService = Depends(get_hca_service),
    caller: User = Depends(get_manager_user),
) -> None:
    """Withdraw a skill an assistant declared about themselves.

    Args:
        hca_id (str): The assistant the skill belongs to.
        skill_id (str): The skill to withdraw.
        service (HcaService): The assistant service.
        caller (User): The authenticated caller; enforces manager access.

    Raises:
        MTSkillNotFound: If the skill does not belong to that assistant;
            answered as a 404.

    Notes:
        - **The supervisors' half of the pair.** A skill is declared by its
          owner and takes effect at once, with no approval step — so this is
          the correction: a manager or an administrator who believes somebody
          has over-claimed can remove it without waiting for them. The owner's
          own route is ``DELETE /api/v1/me/hca/skills/{id}``, and it is the
          only place an assistant may touch a profile at all.
        - ``get_manager_user`` rather than ``get_current_user`` with an
          ownership check, unlike the absence routes beside it. Both roles are
          served, but by two routes with two guards rather than one route whose
          meaning depends on who called it — and a manager reaching this one
          for their *own* record is served by it too, since a manager passes
          the service's ownership check.
        - Withdrawing does not re-plan anything. It applies to the next
          planning run, so a skill removed this afternoon does not cancel a
          visit somebody has already been told to make.
    """
    logger.info(
        "Withdrawing skill %s from assistant %s at the request of %s.",
        skill_id,
        hca_id,
        caller.email,
    )
    await service.remove_skill(hca_id, skill_id, caller)
