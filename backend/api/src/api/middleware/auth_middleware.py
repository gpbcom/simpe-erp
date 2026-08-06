from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Awaitable, Callable, ClassVar, Optional, Tuple

# Third-party imports
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# First-party imports
from api.dependencies import get_auth_service_standalone
from service.auth.exceptions import (
    MTAuthInvalidToken,
    MTAuthMissingSecret,
    MTAuthUserInactive,
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Resolves the bearer token and attaches the account to the request.

    Attributes:
        EXEMPT_PATHS (ClassVar[Tuple[str, ...]]): Path prefixes served without
            a credential.
        PUBLIC_POST_PATHS (ClassVar[Tuple[str, ...]]): Exact paths served
            without a credential for ``POST`` alone.
        PASSWORD_CHANGE_PATH (ClassVar[str]): The one route reachable by an
            account that must still change its temporary password.
        BEARER_PREFIX (ClassVar[str]): The scheme the header must use.
        logger (Logger): Logger for authentication decisions.

    Notes:
        - Authentication happens here rather than in a dependency so that a route
          added without a guard is still authenticated: forgetting a dependency
          would otherwise leave the endpoint open. The *authorisation* decision
          stays in the per-route guards, which is where it belongs.
        - ``/api/v1/auth/me`` is deliberately **not** exempt: it exists to report
          who the caller is, which is meaningless without a credential.
        - **The mandatory password change is enforced here.** An account created
          by an administrator can sign in — it must, in order to change its
          temporary password — and without a check at this level it could then
          do everything else with a credential somebody else typed. Putting the
          check in the middleware rather than in each guard means a route added
          tomorrow is covered by it too.
    """

    EXEMPT_PATHS: ClassVar[Tuple[str, ...]] = (
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        # An applicant has no account yet, and cannot choose a company
        # without seeing the list.
        "/api/v1/companies/choices",
        # A webhook has no signed-in user to authenticate as. It carries a
        # shared secret instead, which the endpoint itself compares.
        "/api/v1/webhooks/",
        "/health",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
    )
    # The only route an account still holding a temporary password may reach.
    # Public for POST only, and matched exactly. Submitting an application is
    # how somebody with no account asks for one; *reading* the queue behind the
    # same prefix is a manager's job. A prefix exemption would have opened the
    # review and decision routes to anybody, which is precisely the mistake
    # this pair of class attributes exists to make impossible.
    #
    # ``/api/v1/companies/registration`` is public for the same reason and with
    # the same care: founding an agency is something a visitor with no account
    # does, while every other route under ``/api/v1/companies`` — listing them,
    # reading one, editing one, opening or closing its applications — stays
    # behind a manager or administrator gate. Matching the exact path rather
    # than the prefix is what keeps that true. The route itself is also inert
    # unless the deployment sets ``auth.allow_company_registration``.
    PUBLIC_POST_PATHS: ClassVar[Tuple[str, ...]] = (
        "/api/v1/hca-applications",
        "/api/v1/companies/registration",
    )
    # The event stream carries its credential in the query string, because
    # EventSource cannot set a header. It verifies that token itself, with a
    # scope this middleware's bearer path deliberately refuses.
    SELF_AUTHENTICATED_PATHS: ClassVar[Tuple[str, ...]] = (
        "/api/v1/notifications/stream",
    )
    PASSWORD_CHANGE_PATH: ClassVar[str] = "/api/v1/auth/password"
    BEARER_PREFIX: ClassVar[str] = "bearer "

    def __init__(self, app: Callable, logger: Optional[Logger] = None) -> None:
        """Initialize the middleware.

        Args:
            app (Callable): The downstream ASGI application.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        super().__init__(app)
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("AuthMiddleware created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _is_exempt(self, path: str, method: str) -> bool:
        """Return whether a request is served without a credential.

        Args:
            path (str): The request path.
            method (str): The HTTP method.

        Returns:
            bool: ``True`` when the path starts with an exempt prefix, or is an
            exact public-POST path reached with ``POST``.

        Notes:
            The method matters for exactly one family. ``POST
            /api/v1/hca-applications`` is how somebody with no account applies
            for one; ``GET`` on the same path is a manager reading the hiring
            queue, and a prefix exemption would have served it to anybody —
            along with the approve and reject routes beneath it.
        """
        if path.startswith(self.EXEMPT_PATHS):
            return True
        if path.rstrip("/") in self.SELF_AUTHENTICATED_PATHS:
            return True
        return method.upper() == "POST" and path.rstrip("/") in self.PUBLIC_POST_PATHS

    def _read_bearer_token(self, request: Request) -> Optional[str]:
        """Extract the bearer token from the Authorization header.

        Args:
            request (Request): The incoming request.

        Returns:
            Optional[str]: The token, or ``None`` when the header is absent,
            uses another scheme, or carries nothing after the scheme.
        """
        header = request.headers.get("Authorization", "")
        if not header.lower().startswith(self.BEARER_PREFIX):
            return None
        token = header[len(self.BEARER_PREFIX) :].strip()
        return token if token else None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],  # noqa: E501
    ) -> Response:
        """Attach the authenticated account, then continue the request.

        Args:
            request (Request): The incoming request.
            call_next (Callable[[Request], Awaitable[Response]]): The next
                handler in the chain.

        Returns:
            Response: The downstream response, or a 401/403/503 when the
            credential could not be resolved.

        Notes:
            - An absent or unreadable credential leaves ``request.state.user``
              unset rather than rejecting outright. The guards then answer 401,
              which keeps the exempt-path list from having to enumerate every
              public route perfectly — a route missing from it degrades to
              "unauthenticated", not to "unreachable".
            - A malformed *present* token is rejected here, though: continuing
              with it silently ignored would let a client believe it was signed
              in when it was not.
        """
        if self._is_exempt(request.url.path, request.method):
            self.logger.debug(
                "Path %s is exempt from authentication.", request.url.path
            )
            return await call_next(request)

        token = self._read_bearer_token(request)
        if token is None:
            self.logger.debug(
                "No bearer credential on %s %s.", request.method, request.url.path
            )
            return await call_next(request)

        try:
            # The session lives only for the lookup. Held open across
            # ``call_next`` it would tie up a pooled connection for the whole
            # request, which is how a busy deployment runs out of them.
            async with get_auth_service_standalone() as service:
                request.state.user = await service.resolve_token(token)
        except MTAuthMissingSecret as exc:
            self.logger.error("Cannot verify tokens: %s.", exc)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Authentication is not configured."},
            )
        except MTAuthUserInactive as exc:
            self.logger.warning("Rejected a token for an inactive account: %s.", exc)
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": str(exc)},
            )
        except MTAuthInvalidToken as exc:
            self.logger.warning("Rejected an invalid token: %s.", exc)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": str(exc)},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as exc:  # noqa: BLE001 - reported as a 503
            # Anything else — the database being down, most likely — means the
            # credential cannot be checked at all. Answering 401 would tell a
            # legitimate caller their token is bad, which it is not.
            self.logger.error("Authentication backend unavailable: %s.", exc)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Authentication backend unavailable."},
            )

        if (
            request.state.user.must_change_password
            and request.url.path != self.PASSWORD_CHANGE_PATH
        ):
            self.logger.warning(
                "Refused %s %s: account %s must change its temporary password first.",
                request.method,
                request.url.path,
                request.state.user.email,
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": (
                        "You must change your temporary password before using "
                        "the application."
                    ),
                    "must_change_password": True,
                },
            )

        self.logger.debug(
            "Authenticated %s %s as %s.",
            request.method,
            request.url.path,
            request.state.user.email,
        )
        return await call_next(request)
