from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, HTTPException, Query, status

# First-party imports
from api.dependencies import (  # noqa: E501
    get_admin_user,
    get_auth_service,
    get_user_repository,
)
from models.auth.user import User
from models.enums import UserRole
from models.schemas.requests.active_update_request import ActiveUpdateRequest
from models.schemas.requests.role_update_request import RoleUpdateRequest
from models.schemas.responses.user_response import UserResponse
from service.auth.auth import AuthService
from storage.repositories.user import UserRepository

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    role: Optional[UserRole] = Query(default=None),
    repository: UserRepository = Depends(get_user_repository),
    _: User = Depends(get_admin_user),
) -> List[UserResponse]:
    """List the accounts.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        role (Optional[UserRole]): Restrict to one role.
        repository (UserRepository): The account store.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        List[UserResponse]: The accounts, without their password hashes.
    """
    logger.info("Listing accounts: page=%d size=%d role=%s.", page, size, role)
    users = await repository.list(page=page, size=size, role=role)
    return [UserResponse.from_user(user) for user in users]


@router.post("/{user_id}/promote", response_model=UserResponse)
async def promote_user(
    user_id: str,
    request: RoleUpdateRequest,
    service: AuthService = Depends(get_auth_service),
    _: User = Depends(get_admin_user),
) -> UserResponse:
    """Change an account's role.

    Args:
        user_id (str): The account to change.
        request (RoleUpdateRequest): The role to grant.
        service (AuthService): The authentication service.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        UserResponse: The updated account.

    Raises:
        MTAuthLastAdmin: If the change would remove the last administrator;
            answered as a 409.
        HTTPException: 404 when the account does not exist.

    Notes:
        The 404 is raised here rather than mapped from an exception: the
        service answers "no such account" with ``None``, and turning that into
        a status is this layer's job.
    """
    user = await service.promote(user_id, request.role)
    if user is None:
        logger.warning("Promotion requested for absent account %s.", user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No account {user_id!r} exists.",
        )
    logger.info("Account %s is now a %s.", user_id, user.role.value)
    return UserResponse.from_user(user)


@router.patch("/{user_id}/active", response_model=UserResponse)
async def set_user_active(
    user_id: str,
    request: ActiveUpdateRequest,
    service: AuthService = Depends(get_auth_service),
    _: User = Depends(get_admin_user),
) -> UserResponse:
    """Enable or disable sign-in for an account.

    Args:
        user_id (str): The account to change.
        request (ActiveUpdateRequest): Whether sign-in is permitted.
        service (AuthService): The authentication service.
        _ (User): The authenticated caller; enforces administrator access.

    Returns:
        UserResponse: The updated account.

    Raises:
        MTAuthLastAdmin: If the change would deactivate the last
            administrator; answered as a 409.
        HTTPException: 404 when the account does not exist.
    """
    user = await service.set_active(user_id, request.is_active)
    if user is None:
        logger.warning("Activation change requested for absent account %s.", user_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No account {user_id!r} exists.",
        )
    logger.info("Account %s active is now %s.", user_id, user.is_active)
    return UserResponse.from_user(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    service: AuthService = Depends(get_auth_service),
    caller: User = Depends(get_admin_user),
) -> None:
    """Remove an account outright.

    Args:
        user_id (str): The account to remove.
        service (AuthService): The authentication service.
        caller (User): The authenticated caller; enforces administrator access
            and is refused their own account.

    Raises:
        MTAuthUnknownAccount: If no such account exists; answered as a 404.
        MTAuthLastAdmin: If this is the last administrator, or the caller's own
            account; answered as a 409.

    Notes:
        **Deactivating is the ordinary way to stop somebody signing in.**
        Removing a person who worked here erases who validated what, so this is
        for accounts that should never have existed: one raised in error, and
        the fixtures a test campaign removes after itself.
    """
    logger.info("Deleting account %s at the request of %s.", user_id, caller.email)
    await service.delete_account(user_id, requested_by=caller)
