from __future__ import annotations

# Standard library imports
from typing import Dict
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import get_manager_user, get_planning_service
from api.exception_handlers import ExceptionHandlers
from api.v1.planning.settings import router as settings_router
from models.auth.user import User
from models.enums import UserRole
from models.settings.planning_settings import PlanningSettings

#: A complete payload. Individual tests override one field at a time, so what
#: each of them is actually asserting stays visible at the call site.
VALID_PAYLOAD: Dict[str, float] = {
    "max_intervention_radius_km": 30.0,
    "day_start_minute": 9 * 60,
    "day_end_minute": 20 * 60,
    "lunch_break_minutes": 60,
    "lunch_window_start_minute": 11 * 60 + 30,
    "lunch_window_end_minute": 14 * 60 + 30,
}


@pytest.fixture
def service() -> AsyncMock:
    """Return a stubbed planning service.

    Returns:
        AsyncMock: The service double, echoing whatever it is asked to store.
    """
    stub = AsyncMock()
    stub.current_settings.return_value = PlanningSettings(
        max_intervention_radius_km=30.0
    )
    stub.update_settings.side_effect = lambda **kwargs: PlanningSettings(
        **{key: value for key, value in kwargs.items() if key != "updated_by"},
        updated_by=kwargs["updated_by"],
    )
    return stub


@pytest.fixture
def client(service: AsyncMock) -> TestClient:
    """Return a client over the settings router alone.

    Args:
        service (AsyncMock): The stubbed planning service.

    Returns:
        TestClient: A client with the service and the guard replaced.

    Notes:
        The production exception handlers are registered, because the endpoint
        lets the payload's own exceptions escape — without them a rejected
        working day would answer 500 here while answering 422 in production.
    """
    caller = User(
        company_id="company-1",
        id="user-1",
        email="manager@example.com",
        full_name="Manager",
        role=UserRole.MANAGER,
    )
    app = FastAPI()
    app.include_router(settings_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_planning_service] = lambda: service
    app.dependency_overrides[get_manager_user] = lambda: caller
    return TestClient(app)


class TestReadingThePlanningSettings:
    """Tests for the rules a manager reads."""

    def test_the_working_day_is_published(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A settings screen cannot show hours the API does not send.

        Args:
            client (TestClient): The client under test.
            service (AsyncMock): The service double.
        """
        service.current_settings.return_value = PlanningSettings(
            max_intervention_radius_km=30.0,
            day_start_minute=8 * 60,
            day_end_minute=19 * 60,
        )
        published = client.get("/api/v1/planning/settings").json()

        assert published["day_start_minute"] == 8 * 60
        assert published["day_end_minute"] == 19 * 60
        assert published["lunch_window_start_minute"] == 11 * 60 + 30
        assert published["lunch_window_end_minute"] == 14 * 60 + 30


class TestChangingThePlanningSettings:
    """Tests for the rules a manager changes."""

    def test_the_whole_working_day_reaches_the_service(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """Every field the manager sent is forwarded, not just the radius.

        Args:
            client (TestClient): The client under test.
            service (AsyncMock): The service double.

        Notes:
            An endpoint that forwarded a subset would answer 200 with the
            values the manager typed echoed back by the payload, while storing
            the defaults — a save that looks successful and changes nothing.
        """
        response = client.put(
            "/api/v1/planning/settings",
            json={
                **VALID_PAYLOAD,
                "day_start_minute": 7 * 60 + 30,
                "day_end_minute": 18 * 60,
                "lunch_window_start_minute": 11 * 60,
                "lunch_window_end_minute": 13 * 60,
            },
        )

        assert response.status_code == 200
        forwarded = service.update_settings.await_args.kwargs
        assert forwarded["day_start_minute"] == 7 * 60 + 30
        assert forwarded["day_end_minute"] == 18 * 60
        assert forwarded["lunch_window_start_minute"] == 11 * 60
        assert forwarded["lunch_window_end_minute"] == 13 * 60

    def test_the_editing_account_is_recorded(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A day that quietly moved is a question with a name attached.

        Args:
            client (TestClient): The client under test.
            service (AsyncMock): The service double.
        """
        client.put("/api/v1/planning/settings", json=VALID_PAYLOAD)

        assert service.update_settings.await_args.kwargs["updated_by"] == "user-1"

    def test_a_radius_only_payload_keeps_the_default_day(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A manager adjusting one rule need not restate the other five.

        Args:
            client (TestClient): The client under test.
            service (AsyncMock): The service double.
        """
        response = client.put(
            "/api/v1/planning/settings",
            json={"max_intervention_radius_km": 45.0},
        )

        assert response.status_code == 200
        forwarded = service.update_settings.await_args.kwargs
        assert forwarded["day_start_minute"] == 9 * 60
        assert forwarded["day_end_minute"] == 20 * 60

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param(
                {"day_start_minute": 20 * 60, "day_end_minute": 9 * 60},
                id="a day that ends before it starts",
            ),
            pytest.param(
                {
                    "lunch_window_start_minute": 14 * 60,
                    "lunch_window_end_minute": 12 * 60,
                },
                id="a lunch window that ends before it starts",
            ),
            pytest.param(
                {
                    "lunch_break_minutes": 120,
                    "lunch_window_start_minute": 12 * 60,
                    "lunch_window_end_minute": 13 * 60,
                },
                id="a window too narrow to hold the break",
            ),
            pytest.param(
                {"day_start_minute": 25 * 60},
                id="a minute past the end of the day",
            ),
            pytest.param(
                {"day_start_minute": "morning"},
                id="a working day that is not a number",
            ),
        ],
    )
    def test_an_unworkable_day_answers_422(
        self, client: TestClient, service: AsyncMock, overrides: Dict[str, object]
    ) -> None:
        """The conflict is named as a 422 rather than left to the solver.

        Args:
            client (TestClient): The client under test.
            service (AsyncMock): The service double.
            overrides (Dict[str, object]): The fields making it unworkable.

        Notes:
            Reaching the solver, the same payload produces a planning run that
            fails at midnight against every visit with "no feasible slot",
            which names nothing a manager can act on.
        """
        response = client.put(
            "/api/v1/planning/settings", json={**VALID_PAYLOAD, **overrides}
        )

        assert response.status_code == 422
        service.update_settings.assert_not_called()

    def test_a_bad_radius_still_answers_422(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """The rule that was already here is not lost to the new ones.

        Args:
            client (TestClient): The client under test.
            service (AsyncMock): The service double.
        """
        response = client.put(
            "/api/v1/planning/settings",
            json={**VALID_PAYLOAD, "max_intervention_radius_km": 0},
        )

        assert response.status_code == 422
        service.update_settings.assert_not_called()
