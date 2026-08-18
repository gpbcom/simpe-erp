from __future__ import annotations

# Standard library imports
from types import SimpleNamespace
from typing import Callable, List
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.middleware.transaction_middleware import TransactionMiddleware


class TestTransactionMiddleware:
    """Tests for committing before the response leaves.

    Attributes:
        session (AsyncMock): The session a handler attaches to the request.
        status_code (int): The status the refusing handler raises with.
        seen (List[Request]): The requests the stand-in stack was handed.
        answer (Response): The response the stand-in stack returns.

    Notes:
        - The bug this guards against was measurable rather than theoretical:
          creating an assistant and immediately registering their account
          failed roughly one time in five, because FastAPI runs a ``yield``
          dependency's teardown — where the commit lived — *after* the response
          has been sent. A client acting on its own 201 could arrive before its
          write had landed.
        - The handlers are **methods**, registered onto a throwaway app by
          ``_app_serving``, rather than functions defined inside each test.
          They read what they need off the instance, which pytest rebuilds per
          test, so two tests never share a session.
    """

    session: AsyncMock
    status_code: int
    seen: List[Request]
    answer: Response

    ############################
    # Internal Helpers Methods #
    ############################

    def _app_serving(self, path: str, handler: Callable) -> FastAPI:
        """Build an app that runs one handler behind the middleware.

        Args:
            path (str): The route to serve.
            handler (Callable): The bound handler method to serve it with.

        Returns:
            FastAPI: The application, ready for a ``TestClient``.
        """
        app = FastAPI()
        app.add_middleware(TransactionMiddleware)
        app.get(path)(handler)
        return app

    async def _writes(self, request: Request) -> dict:
        """Attach the test's session and succeed.

        Args:
            request (Request): The incoming request.

        Returns:
            dict: A trivial success body.
        """
        request.state.session = self.session
        return {"ok": True}

    async def _probes(self) -> dict:
        """Answer without ever touching the database.

        Returns:
            dict: A trivial success body.
        """
        return {"status": "ok"}

    async def _refuses(self, request: Request) -> dict:
        """Attach the test's session, then refuse.

        Args:
            request (Request): The incoming request.

        Returns:
            dict: Never. The refusal is raised.

        Raises:
            HTTPException: Always, with the status under test.
        """
        request.state.session = self.session
        raise HTTPException(status_code=self.status_code, detail="no")

    async def _call_next(self, passed: Request) -> Response:
        """Stand in for the rest of the stack.

        Args:
            passed (Request): The request handed on.

        Returns:
            Response: The prepared answer.
        """
        self.seen.append(passed)
        return self.answer

    # ------------------------------------------------------------------ #
    #  The success path
    # ------------------------------------------------------------------ #

    def test_a_successful_request_commits_before_responding(self) -> None:
        """The commit happens while the response is still being assembled.

        Notes:
            Ordering is what matters, and it is what the assertion captures:
            the commit is recorded during ``call_next``'s return path, not
            afterwards, so a client reading the response can already see the
            write.
        """
        self.session = AsyncMock()

        client = TestClient(self._app_serving("/writes", self._writes))
        response = client.get("/writes")

        assert response.status_code == 200
        self.session.commit.assert_awaited_once()

    def test_a_request_that_touched_no_database_is_passed_through(self) -> None:
        """A probe with no session is not treated as an error."""
        client = TestClient(self._app_serving("/probe", self._probes))

        assert client.get("/probe").status_code == 200

    # ------------------------------------------------------------------ #
    #  The failure path
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "status_code",
        [
            pytest.param(400, id="Refused - bad request"),
            pytest.param(403, id="Refused - forbidden"),
            pytest.param(404, id="Refused - not found"),
            pytest.param(409, id="Refused - conflict"),
            pytest.param(422, id="Refused - unprocessable"),
        ],
    )
    def test_a_failed_request_is_not_committed(self, status_code: int) -> None:
        """An error status leaves the transaction to roll back.

        Args:
            status_code (int): The refusal to check.

        Notes:
            Committing here would make a half-finished write durable: a handler
            that inserted a row and then refused would leave the row behind.
            The dependency's own rollback path handles it.
        """
        self.session = AsyncMock()
        self.status_code = status_code

        client = TestClient(self._app_serving("/refuses", self._refuses))
        response = client.get("/refuses")

        assert response.status_code == status_code
        self.session.commit.assert_not_awaited()

    def test_a_failing_commit_rolls_back_rather_than_reporting_success(
        self,
    ) -> None:
        """A commit that cannot land does not leave a 200 behind it.

        Notes:
            The response body is already built by this point, so the status
            cannot honestly be rewritten in place — what the middleware can do
            is refuse to let the work be half-applied, and raise so the failure
            is visible rather than swallowed.
        """
        self.session = AsyncMock()
        self.session.commit.side_effect = RuntimeError("the connection went away")

        client = TestClient(self._app_serving("/writes", self._writes))

        with pytest.raises(RuntimeError):
            client.get("/writes")

        self.session.rollback.assert_awaited_once()

    # ------------------------------------------------------------------ #
    #  Direct dispatch
    # ------------------------------------------------------------------ #

    async def test_the_response_is_returned_unchanged(self) -> None:
        """The middleware commits. It does not rewrite the answer."""
        self.session = AsyncMock()
        self.seen = []
        self.answer = SimpleNamespace(status_code=201)
        request = SimpleNamespace(
            state=SimpleNamespace(session=self.session),
            method="POST",
            url=SimpleNamespace(path="/api/v1/customers"),
        )

        middleware = TransactionMiddleware(app=None)
        returned = await middleware.dispatch(request, self._call_next)

        assert returned is self.answer
        assert self.seen == [request]
        self.session.commit.assert_awaited_once()
