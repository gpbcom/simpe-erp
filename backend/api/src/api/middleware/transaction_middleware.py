from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Awaitable, Callable, Optional

# Third-party imports
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware


class TransactionMiddleware(BaseHTTPMiddleware):
    """Commits the request's transaction before the response leaves.

    Attributes:
        logger (Logger): Logger for transaction decisions.

    Notes:
        - **This exists because of when FastAPI runs dependency teardown.** A
          dependency declared with ``yield`` has its exit code — here, the commit
          in :meth:`DatabaseConnectionManager.session` — executed *after* the
          response has been sent. A client that issues its next request straight
          away can therefore arrive before its own write has landed, and read a
          database that does not yet contain what it was just told was created.
        - That is not theoretical: creating an assistant and immediately
          registering their account failed roughly one time in five, with the
          registration reporting that the assistant did not exist.
        - Committing here closes the window. ``call_next`` returns once the
          handler has produced its response but before the body is written
          downstream, so a commit at this point is durable before the client can
          act on the answer. The dependency's own commit still runs afterwards
          and finds nothing outstanding.
        - Nothing is committed for a failed response. An error status means
          either a domain exception the handler translated or a guard that
          refused, and in both cases the partial work must go back — which the
          dependency's rollback path already does.
    """

    def __init__(self, app: Callable, logger: Optional[Logger] = None) -> None:
        """Initialize the middleware.

        Args:
            app (Callable): The next application in the stack.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        super().__init__(app)
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("TransactionMiddleware created.")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],  # noqa: E501
    ) -> Response:
        """Run the request, then commit its transaction if it succeeded.

        Args:
            request (Request): The incoming request.
            call_next (Callable[[Request], Awaitable[Response]]): The rest of
                the stack.

        Returns:
            Response: The handler's response, unchanged.

        Notes:
            The session is found on ``request.state``, where
            :func:`api.dependencies.get_session` puts it. A request that never
            touched the database — a probe, a 404 — has none, and is passed
            straight through.
        """
        response = await call_next(request)

        session: Optional[AsyncSession] = getattr(request.state, "session", None)  # noqa: E501
        if session is None:
            return response
        if response.status_code >= 400:
            self.logger.debug(
                "Leaving the transaction for %s %s to roll back: status %d.",
                request.method,
                request.url.path,
                response.status_code,
            )
            return response

        try:
            await session.commit()
            self.logger.debug(
                "Committed the transaction for %s %s before responding.",
                request.method,
                request.url.path,
            )
        except Exception as exc:  # noqa: BLE001 - the response is already built
            # The handler has already produced a success response, so the
            # status cannot honestly be changed here without discarding it.
            # What can be done is refuse to report success on a write that did
            # not land: the session is rolled back and the failure recorded.
            await session.rollback()
            self.logger.error(
                "Could not commit %s %s; the work was rolled back: %s",
                request.method,
                request.url.path,
                exc,
            )
            raise
        return response
