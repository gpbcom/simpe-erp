from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends, status

# First-party imports
from api.dependencies import get_auth_service, get_current_user
from models.auth.access_token import AccessToken
from models.auth.user import User
from models.enums import UserRole
from models.schemas.requests.login_request import LoginRequest
from models.schemas.requests.register_request import RegisterRequest
from models.schemas.responses.user_response import UserResponse
from service.auth.auth import AuthService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    request: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Create an assistant account.

    Args:
        request (RegisterRequest): The account to create.
        service (AuthService): The authentication service.

    Returns:
        UserResponse: The new account, without its password hash.

    Raises:
        MTAuthEmailAlreadyRegistered: If the address is already registered;
            answered as a 409.
        MTAuthHcaLinkRequired: If the account names no assistant record;
            answered as a 422.
        MTAuthUnknownHca: If it names a record that does not exist; answered
            as a 422.

    Notes:
        **The role is not taken from the payload, and cannot be.** This is the
        one route that creates an account without a credential, so honouring a
        role sent with the request would let anybody register themselves an
        administrator. It always grants :attr:`~models.enums.UserRole.HCA`; a
        manager or an administrator is created through the manager-gated
        ``POST /api/v1/auth/accounts``.
    """
    logger.info("Registering an assistant account for %s.", request.email)
    user = await service.register(
        email=str(request.email),
        full_name=request.full_name,
        password=request.password,
        role=UserRole.HCA,
        hca_id=request.hca_id,
    )
    return UserResponse.from_user(user)


@router.post("/login", response_model=AccessToken)
async def login(
    request: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AccessToken:
    """Sign in and receive an access token.

    Args:
        request (LoginRequest): The credentials.
        service (AuthService): The authentication service.

    Returns:
        AccessToken: The signed token and its lifetime.

    Raises:
        MTAuthInvalidCredentials: If the address or password does not match;
            answered as a 401 carrying the ``WWW-Authenticate`` challenge.
        MTAuthUserInactive: If the account is deactivated; answered as a 403.
        MTAuthMissingSecret: If signing is not configured; answered as a 503.

    Notes:
        The 401 carries the same message whether the address is unknown or the
        password is wrong, so the endpoint cannot be used to discover which
        addresses are registered.
    """
    logger.debug("Signing in %s.", request.email)
    user = await service.authenticate(
        email=str(request.email), password=request.password
    )
    return await service.issue_token(user)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    """Report the account the caller is signed in as.

    Args:
        user (User): The authenticated caller.

    Returns:
        UserResponse: The account, without its password hash.

    Notes:
        The guard is taken as a dependency rather than called inside the body.
        Both authenticate identically at run time, but only the dependency form
        can be replaced in a test, which is what lets the endpoint be exercised
        without mounting the authentication middleware.
    """
    logger.debug("Reporting the current account %s.", user.id)
    return UserResponse.from_user(user)


@router.post("/stream-token", response_model=AccessToken)
async def issue_stream_token(
    service: AuthService = Depends(get_auth_service),
    caller: User = Depends(get_current_user),
) -> AccessToken:
    """Mint a short-lived credential for the notification event stream.

    Args:
        service (AuthService): The authentication service.
        caller (User): The authenticated caller.

    Returns:
        AccessToken: The stream token and its lifetime, in seconds.

    Raises:
        MTAuthMissingSecret: If the signing secret is not configured; answered
            as a 503.

    Notes:
        ``EventSource`` cannot set an ``Authorization`` header, so a browser can
        only authenticate a stream through the URL. Rather than put the
        twelve-hour session token there — where it would reach referrer headers,
        proxy logs and browser history — the client exchanges it here for one
        that lives a minute and is refused on every other route.
    """
    logger.debug("Issuing a stream token for %s.", caller.email)
    return service.issue_stream_token(caller)
