from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import get_admin_user, get_current_user, get_team_service
from models.auth.user import User
from models.enums import MemberKind
from models.organisation.team.team_member import TeamMember
from models.schemas.requests.organisation.team_create_request import (
    TeamCreateRequest,
)
from models.schemas.requests.organisation.team_update_request import (
    TeamUpdateRequest,
)
from models.schemas.responses.organisation.team_view import TeamView
from service.organisation.teams import TeamService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/teams", tags=["Teams"])


@router.post("", response_model=TeamView, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreateRequest,
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_admin_user),
) -> TeamView:
    """Form a team at one of the company's sites.

    Args:
        payload (TeamCreateRequest): The team's name, site and manager.
        service (TeamService): The team service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        TeamView: The stored team, whose manager is already its one member.

    Raises:
        MTTeamNameTaken: If the company already has a team of that name; 409.
        MTTeamManagerRequired: If the named account cannot run it; 422.
        MTTeamMemberAlreadyPlaced: If the manager is already on a team; 409.

    Notes:
        Administrator-only, as the requirement states — a manager cannot form
        the team they would then run. The member count is one because the
        creating call enrols the manager, which is why it is passed rather than
        queried.
    """
    logger.info("Forming team %r for company %s.", payload.name, caller.company_id)  # noqa: E501
    team = await service.create(payload.to_team(caller.company_id), caller)
    return TeamView.from_team(team, member_count=1)


@router.get("", response_model=List[TeamView])
async def list_teams(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_current_user),
) -> List[TeamView]:
    """List the teams the caller may read.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        service (TeamService): The team service.
        caller (User): The authenticated caller.

    Returns:
        List[TeamView]: An administrator's whole company, a manager's own teams,
        or the single team an assistant is on.

    Notes:
        The narrowing is **the service's**, not the route's, and it is applied in
        the statement rather than to the page. A guard here could only prove the
        caller's rank; which rows a manager may see is a question about the teams
        table, and a page filtered after the read has already loaded rows the
        caller may not see.
    """
    logger.debug("Listing teams for %s: page=%d.", caller.email, page)
    return await service.views(caller, page=page, size=size)


@router.get("/{team_id}", response_model=TeamView)
async def get_team(
    team_id: str,
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_current_user),
) -> TeamView:
    """Return one team the caller may read.

    Args:
        team_id (str): The team to read.
        service (TeamService): The team service.
        caller (User): The authenticated caller.

    Returns:
        TeamView: The team and its member count.

    Raises:
        MTTeamNotFound: If no such team exists; answered as a 404.
        MTTeamForbidden: If it is not one the caller may read; 403.
    """
    logger.debug("Reading team %s for %s.", team_id, caller.email)
    return await service.view(team_id, caller)


@router.put("/{team_id}", response_model=TeamView)
async def update_team(
    team_id: str,
    payload: TeamUpdateRequest,
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_admin_user),
) -> TeamView:
    """Change a team's name, site or manager.

    Args:
        team_id (str): The team to change.
        payload (TeamUpdateRequest): The new name, site and manager.
        service (TeamService): The team service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        TeamView: The updated team.

    Raises:
        MTTeamNotFound: If no such team exists; answered as a 404.
        MTTeamNameTaken: If another team already uses the name; 409.
        MTTeamManagerRequired: If the named account cannot run it; 422.
    """
    logger.info("Updating team %s at the request of %s.", team_id, caller.email)  # noqa: E501
    await service.update(payload.to_team(team_id, caller.company_id), caller)
    return await service.view(team_id, caller)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str,
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_admin_user),
) -> None:
    """Disband a team that holds no work.

    Args:
        team_id (str): The team to remove.
        service (TeamService): The team service.
        caller (User): The authenticated caller; enforces administrator access.

    Raises:
        MTTeamNotFound: If no such team exists; answered as a 404.
        MTTeamHasWork: If quotes still name it; answered as a 409.

    Notes:
        The team's shared documents are **not** removed here, and that is a gap
        this route knows about: emptying the object store belongs to
        :meth:`~service.organisation.team_documents.TeamDocumentService.purge_team`,
        which the disband screen calls first. Wiring it into the delete itself
        would put an object-store failure in the path of a database transaction.
    """
    logger.info("Disbanding team %s at the request of %s.", team_id, caller.email)  # noqa: E501
    await service.delete(team_id, caller)


@router.get("/{team_id}/members", response_model=List[TeamMember])
async def list_team_members(
    team_id: str,
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_current_user),
) -> List[TeamMember]:
    """Return everybody on a team the caller may read.

    Args:
        team_id (str): The team to read.
        service (TeamService): The team service.
        caller (User): The authenticated caller.

    Returns:
        List[TeamMember]: The memberships, each a kind and an identifier.

    Raises:
        MTTeamNotFound: If no such team exists; answered as a 404.
        MTTeamForbidden: If it is not one the caller may read; 403.
    """
    logger.debug("Listing the members of team %s for %s.", team_id, caller.email)  # noqa: E501
    return await service.members(team_id, caller)


@router.post(
    "/{team_id}/members",
    response_model=TeamMember,
    status_code=status.HTTP_201_CREATED,
)
async def add_team_member(
    team_id: str,
    member: TeamMember,
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_admin_user),
) -> TeamMember:
    """Put somebody on a team.

    Args:
        team_id (str): The team they join.
        member (TeamMember): Which person, and which kind of record.
        service (TeamService): The team service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        TeamMember: The stored membership.

    Raises:
        MTTeamNotFound: If no such team exists; answered as a 404.
        MTTeamMemberAlreadyPlaced: If they are already on a team; 409.
        MTTeamMemberOutsideAgency: If they do not work at the team's site; 422.

    Notes:
        Adding somebody is a **single act**, not a submitted roster, which is the
        one place this surface departs from the "send the whole list" rule used
        for working days. A person is on exactly one team, so a whole-list
        submission would silently take people off other teams — and each of those
        removals changes whose week the next planning run rewrites.
    """
    logger.info(
        "Putting %s %s on team %s at the request of %s.",
        member.member_kind.value,
        member.member_id,
        team_id,
        caller.email,
    )
    return await service.add_member(team_id, member, caller)


@router.delete(
    "/{team_id}/members/{member_kind}/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_team_member(
    team_id: str,
    member_kind: MemberKind,
    member_id: str,
    service: TeamService = Depends(get_team_service),
    caller: User = Depends(get_admin_user),
) -> None:
    """Take somebody off a team.

    Args:
        team_id (str): The team they leave.
        member_kind (MemberKind): Whether the identifier names an account or an
            assistant record.
        member_id (str): The person to remove.
        service (TeamService): The team service.
        caller (User): The authenticated caller; enforces administrator access.

    Raises:
        MTTeamNotFound: If no such team exists, or they are not on it; 404.
        MTTeamManagerRequired: If they are the team's manager; answered as a
            422, because the way to replace a manager is to name a new one.
    """
    logger.info(
        "Taking %s %s off team %s at the request of %s.",
        member_kind.value,
        member_id,
        team_id,
        caller.email,
    )
    await service.remove_member(team_id, member_kind, member_id, caller)
