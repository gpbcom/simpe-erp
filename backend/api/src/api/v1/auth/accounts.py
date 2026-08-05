from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends, status

# First-party imports
from api.dependencies import get_auth_service, get_current_user, get_manager_user
from models.auth.user import User
from models.schemas.requests.password_change_request import PasswordChangeRequest
from models.schemas.requests.staff_account_request import StaffAccountRequest
from models.schemas.responses.temporary_credentials_response import (
    TemporaryCredentialsResponse,
)
from models.schemas.responses.user_response import UserResponse
from service.auth.auth import AuthService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Accounts"])


@router.post(
    "/accounts",
    response_model=TemporaryCredentialsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_staff_account(
    payload: StaffAccountRequest,
    service: AuthService = Depends(get_auth_service),
    caller: User = Depends(get_manager_user),
) -> TemporaryCredentialsResponse:
    """Create an assistant's account on their behalf, with a one-time password.

    Args:
        payload (StaffAccountRequest): The assistant record, address and name.
        service (AuthService): The authentication service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        TemporaryCredentialsResponse: The account and the temporary password,
        in plain text, returned **once**.

    Raises:
        MTAuthUnknownHca: If the assistant record does not exist; 422.
        MTAuthEmailAlreadyRegistered: If the address is taken; 409.

    Notes:
        This is the second of the two ways an assistant account comes to exist.
        The password is generated server-side and shown here once — the stored
        form is a hash, so an administrator who loses it regenerates rather
        than looks it up.

        The account cannot do anything until that password is changed. That is
        not a client-side convention: :class:`AuthMiddleware` refuses every
        request such an account makes except the change itself.
    """
    logger.info(
        "Creating a staff-issued account for %s, requested by %s.",
        payload.email,
        caller.email,
    )
    user, temporary_password = await service.create_staff_account(
        email=str(payload.email),
        full_name=payload.full_name,
        hca_id=payload.hca_id,
        company_id=payload.company_id if payload.company_id else caller.company_id,
    )
    return TemporaryCredentialsResponse(
        user_id=user.id if user.id else "",
        email=str(user.email),
        temporary_password=temporary_password,
        must_change_password=user.must_change_password,
    )


@router.post("/password", response_model=UserResponse)
async def change_password(
    payload: PasswordChangeRequest,
    service: AuthService = Depends(get_auth_service),
    caller: User = Depends(get_current_user),
) -> UserResponse:
    """Replace your own password, clearing any forced-change flag.

    Args:
        payload (PasswordChangeRequest): The current and new passwords.
        service (AuthService): The authentication service.
        caller (User): The authenticated caller.

    Returns:
        UserResponse: The account, without its credential.

    Raises:
        MTAuthInvalidCredentials: If the current password is wrong; 401.
        MTAuthSamePassword: If the new password repeats the old one; 409.

    Notes:
        **The one route an account with a temporary password may reach.**
        Everything else is refused until this succeeds, which is what makes the
        change mandatory rather than advisory — see
        :class:`~api.middleware.auth_middleware.AuthMiddleware`.

        Available to every authenticated account, not only staff-created ones:
        anybody may change their own password, and having one route for both
        means the mandatory path is the same well-worn one.
    """
    logger.info("Changing the password for %s.", caller.email)
    updated = await service.change_password(
        caller, payload.current_password, payload.new_password
    )
    return UserResponse(**updated.to_public_dict())
