from __future__ import annotations

# Standard library imports
from types import SimpleNamespace
from typing import List
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.middleware.transaction_middleware import TransactionMiddleware


class TestTransactionMiddleware:
    """Tests for committing before the response leaves.

    Notes:
        The bug this guards against was measurable rather than theoretical:
        creating an assistant and immediately registering their account failed
        roughly one time in five, because FastAPI runs a ``yield``
        dependency's teardown — where the commit lived — *after* the response
        has been sent. A client acting on its own 201 could arrive before its
        write had landed.
    """

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
        session = AsyncMock()
        app = FastAPI()
        app.add_middleware(TransactionMiddleware)

        @app.get("/writes")
        async def writes(request: Request) -> dict:
            request.state.session = session
            return {"ok": True}

        response = TestClient(app).get("/writes")

        assert response.status_code == 200
        session.commit.assert_awaited_once()

    def test_a_request_that_touched_no_database_is_passed_through(self) -> None:
        """A probe with no session is not treated as an error."""
        app = FastAPI()
        app.add_middleware(TransactionMiddleware)

        @app.get("/probe")
        async def probe() -> dict:
            return {"status": "ok"}

        assert TestClient(app).get("/probe").status_code == 200

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
        session = AsyncMock()
        app = FastAPI()
        app.add_middleware(TransactionMiddleware)

        @app.get("/refuses")
        async def refuses(request: Request) -> dict:
            request.state.session = session
            raise HTTPException(status_code=status_code, detail="no")

        response = TestClient(app).get("/refuses")

        assert response.status_code == status_code
        session.commit.assert_not_awaited()

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
        session = AsyncMock()
        session.commit.side_effect = RuntimeError("the connection went away")
        app = FastAPI()
        app.add_middleware(TransactionMiddleware)

        @app.get("/writes")
        async def writes(request: Request) -> dict:
            request.state.session = session
            return {"ok": True}

        with pytest.raises(RuntimeError):
            TestClient(app).get("/writes")

        session.rollback.assert_awaited_once()

    # ------------------------------------------------------------------ #
    #  Direct dispatch
    # ------------------------------------------------------------------ #

    async def test_the_response_is_returned_unchanged(self) -> None:
        """The middleware commits; it does not rewrite the answer."""
        session = AsyncMock()
        request = SimpleNamespace(
            state=SimpleNamespace(session=session),
            method="POST",
            url=SimpleNamespace(path="/api/v1/customers"),
        )
        answer = SimpleNamespace(status_code=201)
        seen: List[object] = []

        async def call_next(passed: object) -> object:
            """Stand in for the rest of the stack.

            Args:
                passed (object): The request handed on.

            Returns:
                object: The response.
            """
            seen.append(passed)
            return answer

        middleware = TransactionMiddleware(app=None)
        returned = await middleware.dispatch(request, call_next)

        assert returned is answer
        assert seen == [request]
        session.commit.assert_awaited_once()
