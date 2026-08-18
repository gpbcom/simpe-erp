from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, status

# First-party imports
from api.dependencies import get_admin_user, get_agency_service, get_current_user
from models.auth.user import User
from models.enums import MemberKind
from models.organisation.agency.agency_member import AgencyMember
from models.schemas.requests.organisation.agency_create_request import (
    AgencyCreateRequest,
)
from models.schemas.requests.organisation.agency_update_request import (
    AgencyUpdateRequest,
)
from models.schemas.responses.organisation.agency_view import AgencyView
from service.organisation.agencies import AgencyService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/agencies", tags=["Agencies"])


@router.post("", response_model=AgencyView, status_code=status.HTTP_201_CREATED)
async def create_agency(
    payload: AgencyCreateRequest,
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_admin_user),
) -> AgencyView:
    """Open a new site for the caller's company.

    Args:
        payload (AgencyCreateRequest): The site's name, address and type.
        service (AgencyService): The site service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        AgencyView: The stored site, with no member and no team yet.

    Raises:
        MTAgencyNameTaken: If the company already has a site of that name;
            answered as a 409.
        MTAgencyHeadquartersProtected: If it would be a second head office;
            answered as a 409.

    Notes:
        - Administrator-only, as the requirement states. A site decides where
          teams are based and therefore which household's work each team is
          given. A manager able to open one could create a place that quietly
          takes work away from theirs.
        - The counts are passed as zero rather than queried. A site that has
          just been created has neither members nor teams, and reading the
          database to learn that would be a query whose answer is already known.
    """
    logger.info("Opening site %r for company %s.", payload.name, caller.company_id)
    agency = await service.create(payload.to_agency(caller.company_id), caller)
    return AgencyView.from_agency(agency)


@router.get("", response_model=List[AgencyView])
async def list_agencies(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_current_user),
) -> List[AgencyView]:
    """List the sites the caller's company operates from.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        service (AgencyService): The site service.
        caller (User): The authenticated caller.

    Returns:
        List[AgencyView]: The sites, by name, with their member and team counts.

    Notes:
        Open to **every signed-in account**, unlike the writes. An assistant
        reads which site they are attached to, and a manager picks one when
        forming a team. What that costs is bounded by the response model: a site
        record inherits its company's SIRET and bank account, and
        :class:`~models.schemas.responses.organisation.agency_view.AgencyView`
        declares neither.
    """
    logger.debug("Listing sites for %s: page=%d.", caller.email, page)
    return await service.views(caller, page=page, size=size)


@router.get("/{agency_id}", response_model=AgencyView)
async def get_agency(
    agency_id: str,
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_current_user),
) -> AgencyView:
    """Return one of the caller's company's sites.

    Args:
        agency_id (str): The site to read.
        service (AgencyService): The site service.
        caller (User): The authenticated caller.

    Returns:
        AgencyView: The site and its two counts.

    Raises:
        MTAgencyNotFound: If no such site exists. Answered as a 404.
        MTAgencyForbidden: If it belongs to another company. Answered as a 403.
    """
    logger.debug("Reading site %s for %s.", agency_id, caller.email)
    return await service.view(agency_id, caller)


@router.put("/{agency_id}", response_model=AgencyView)
async def update_agency(
    agency_id: str,
    payload: AgencyUpdateRequest,
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_admin_user),
) -> AgencyView:
    """Change a site's name, address or type.

    Args:
        agency_id (str): The site to change.
        payload (AgencyUpdateRequest): The new name, address and type.
        service (AgencyService): The site service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        AgencyView: The updated site.

    Raises:
        MTAgencyNotFound: If no such site exists. Answered as a 404.
        MTAgencyForbidden: If it belongs to another company. Answered as a 403.
        MTAgencyNameTaken: If another site already uses the name; 409.
        MTAgencyHeadquartersProtected: If the change would move or duplicate the
            head office. Answered as a 409.
    """
    logger.info("Updating site %s at the request of %s.", agency_id, caller.email)
    await service.update(payload.to_agency(agency_id, caller.company_id), caller)
    return await service.view(agency_id, caller)


@router.delete("/{agency_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agency(
    agency_id: str,
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_admin_user),
) -> None:
    """Close a site nobody works at.

    Args:
        agency_id (str): The site to remove.
        service (AgencyService): The site service.
        caller (User): The authenticated caller; enforces administrator access.

    Raises:
        MTAgencyNotFound: If no such site exists. Answered as a 404.
        MTAgencyForbidden: If it belongs to another company. Answered as a 403.
        MTAgencyNotEmpty: If teams or people are still attached; 409.
        MTAgencyHeadquartersProtected: If it is the head office and the company
            still operates from elsewhere. Answered as a 409.
    """
    logger.info("Closing site %s at the request of %s.", agency_id, caller.email)
    await service.delete(agency_id, caller)


@router.get("/{agency_id}/members", response_model=List[AgencyMember])
async def list_agency_members(
    agency_id: str,
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_current_user),
) -> List[AgencyMember]:
    """Return everybody attached to a site.

    Args:
        agency_id (str): The site to read.
        service (AgencyService): The site service.
        caller (User): The authenticated caller.

    Returns:
        List[AgencyMember]: The memberships, each a kind and an identifier.

    Raises:
        MTAgencyNotFound: If no such site exists. Answered as a 404.
        MTAgencyForbidden: If it belongs to another company. Answered as a 403.

    Notes:
        A membership carries no name, telephone number or address — only which
        kind of record it points at and which one. Resolving the people is the
        client's job, from the account and assistant lists it already holds and
        is separately authorised to read.
    """
    logger.debug("Listing the members of site %s for %s.", agency_id, caller.email)
    return await service.members(agency_id, caller)


@router.post(
    "/{agency_id}/members",
    response_model=AgencyMember,
    status_code=status.HTTP_201_CREATED,
)
async def add_agency_member(
    agency_id: str,
    member: AgencyMember,
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_admin_user),
) -> AgencyMember:
    """Attach somebody to a site, moving them off whichever one they were on.

    Args:
        agency_id (str): The site they join.
        member (AgencyMember): Which person, and which kind of record.
        service (AgencyService): The site service.
        caller (User): The authenticated caller; enforces administrator access.

    Returns:
        AgencyMember: The stored membership.

    Raises:
        MTAgencyNotFound: If no such site exists. Answered as a 404.
        MTAgencyForbidden: If it belongs to another company. Answered as a 403.
        MTAgencyMemberRunsATeam: If they run a team based at the site they are
            leaving. Answered as a 409.

    Notes:
        - **A transfer, in one call.** Somebody moving site does it once, on one
          screen; requiring a detach first would be two forms for one act, and
          the state in between — a person attached to no site — is one nothing
          else expects. Everybody belongs to exactly one site either way. The
          only question was whether the operator had to do the removal by hand.
        - Their **team goes with the old site**, because a team is people at a
          place and the planner measures every round from it. The one refusal
          left is somebody who *runs* a team there: a team's manager is
          required, so there is no state in which it briefly has none.
        - The body is the model itself rather than a request schema, and that is
          safe here for the reason it is not on the site: an
          :class:`~models.organisation.agency.agency_member.AgencyMember` carries
          a kind and an identifier and nothing else, so there is no field a
          payload could forge. The site comes from the path.
    """
    logger.info(
        "Attaching %s %s to site %s at the request of %s.",
        member.member_kind.value,
        member.member_id,
        agency_id,
        caller.email,
    )
    return await service.add_member(agency_id, member, caller)


@router.delete(
    "/{agency_id}/members/{member_kind}/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_agency_member(
    agency_id: str,
    member_kind: MemberKind,
    member_id: str,
    service: AgencyService = Depends(get_agency_service),
    caller: User = Depends(get_admin_user),
) -> None:
    """Detach somebody from a site.

    Args:
        agency_id (str): The site they leave.
        member_kind (MemberKind): Whether the identifier names an account or an
            assistant record.
        member_id (str): The person to detach.
        service (AgencyService): The site service.
        caller (User): The authenticated caller; enforces administrator access.

    Raises:
        MTAgencyNotFound: If no such site exists, or the person is not attached
            to it. Answered as a 404.
        MTAgencyForbidden: If it belongs to another company. Answered as a 403.

    Notes:
        The kind is in the path rather than the query string because it is half
        of the identity: an account and an assistant record can share an
        identifier, and a route that took only the second would remove whichever
        the store found first.
    """
    logger.info(
        "Detaching %s %s from site %s at the request of %s.",
        member_kind.value,
        member_id,
        agency_id,
        caller.email,
    )
    await service.remove_member(agency_id, member_kind, member_id, caller)
