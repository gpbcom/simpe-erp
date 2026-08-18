from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_current_user,
    get_event_publisher,
    get_hca_service,
    get_team_service,
    get_manager_user,
    get_planning_service,
)
from api.main import app
from models.auth.user import User
from models.enums import (
    AvailabilityKind,
    ContractType,
    PlanningRunStatus,
    UserRole,
    Weekday,
)
from models.planning.planning_run import PlanningRun
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.hca import Hca
from service.hcas.exceptions import MTHcaHasAccount, MTHcaNotFound
from service.hcas.hcas import HcaService
from tests.annotations import ModelInput


def _hca(hca_id: str = "hca-1") -> Hca:
    """Build a geocoded assistant.

    Args:
        hca_id (str): The identifier to assign.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        company_id="company-1",
        id=hca_id,
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email=f"{hca_id}@example.com",
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8566,
            "longitude": 2.3522,
        },
        contract_type=ContractType.CDI,
    )


@pytest.fixture
def service() -> MagicMock:
    """Return a stubbed assistant service.

    Returns:
        MagicMock: A service whose every method is awaitable.
    """
    return MagicMock(spec=HcaService)


@pytest.fixture
def plannings() -> AsyncMock:
    """Return a planning service reporting nobody has future work.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.future_period_for_hca.return_value = None
    return stub


@pytest.fixture
def client(service: MagicMock, plannings: AsyncMock) -> TestClient:
    """Return a client over the production application.

    Args:
        service (MagicMock): The stubbed assistant service.
        plannings (AsyncMock): The stubbed planning service.

    Returns:
        TestClient: A client with the service and the guard replaced.

    Notes:
        The **production** app is used rather than a hand-mounted one, because
        what several of these tests check is the order its routers are included
        in. Mounting them here would test this file's ordering, not the one
        that ships.
    """
    caller = User(
        company_id="company-1",
        id="user-1",
        email="manager@example.com",
        full_name="Manager",
        role=UserRole.MANAGER,
    )
    app.dependency_overrides[get_hca_service] = lambda: service
    app.dependency_overrides[get_manager_user] = lambda: caller
    # The absence endpoints guard on the signed-in caller rather than on a
    # manager: an assistant files their own, and the service compares the
    # caller against the assistant named in the path.
    app.dependency_overrides[get_current_user] = lambda: caller
    # Removing an assistant ends in a replan, so the route reaches the planning
    # service and the broker. The default double reports no future work, which
    # is the 204 path. The replan test replaces it.
    app.dependency_overrides[get_planning_service] = lambda: plannings
    app.dependency_overrides[get_event_publisher] = lambda: AsyncMock()
    # The workforce list narrows to the teams the caller runs, so the route
    # reaches the team service. This double is an administrator's answer —
    # `None` means every assistant — which keeps these fixtures asserting what
    # they were written to assert. The narrowing itself is tested where it
    # lives.
    teams = AsyncMock()
    teams.readable_hca_ids.return_value = None
    app.dependency_overrides[get_team_service] = lambda: teams
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class TestHcaRouteOrdering:
    """Tests for the two routers sharing the /api/v1/hcas prefix."""

    def test_the_photo_constraints_route_is_reachable(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A literal path must not be swallowed by a parameterised one.

        Notes:
            ``GET /photo-constraints`` and ``GET /{hca_id}`` both match the
            same URL. Whichever router is included first wins, so including the
            assistant router before the photograph one turns this endpoint into
            "no assistant 'photo-constraints' exists" — a 404 for a route that
            has nothing to do with an assistant.
        """
        service.get = AsyncMock(side_effect=AssertionError("get_hca was reached"))
        response = client.get("/api/v1/hcas/photo-constraints")
        assert response.status_code == 200
        assert "max_upload_bytes" in response.json()
        service.get.assert_not_awaited()

    def test_an_identifier_still_reaches_the_assistant_route(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """Ordering the routers must not cost the parameterised route."""
        service.get = AsyncMock(return_value=_hca())
        response = client.get("/api/v1/hcas/hca-1")
        assert response.status_code == 200
        assert response.json()["id"] == "hca-1"


class TestHcaEndpoints:
    """Tests for the assistant endpoints themselves."""

    def test_creating_an_assistant_answers_201(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A registered assistant comes back with its identifier."""
        service.create = AsyncMock(return_value=_hca())
        response = client.post(
            "/api/v1/hcas", json=_hca(hca_id="hca-9").model_dump(mode="json")
        )
        assert response.status_code == 201
        assert response.json()["id"] == "hca-1"

    def test_the_published_shape_is_the_response_schema(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """Every assistant leaves through HcaResponse, photographs included.

        Notes:
            The photograph endpoints already published that shape. An
            assistant read through ``GET /{hca_id}`` returning the domain model
            instead would give the same resource two shapes depending on which
            endpoint a client happened to call.
        """
        service.get = AsyncMock(return_value=_hca())
        published = client.get("/api/v1/hcas/hca-1").json()
        assert set(published) == {
            "id",
            "first_name",
            "last_name",
            "phone_number",
            "email",
            "address",
            "contract_type",
            "certifications",
            "skills",
            "driving_license",
            "photo_url",
            "availability",
            "working_weekdays",
            "field_employee",
            "created_at",
            "updated_at",
        }

    def test_listing_publishes_the_same_shape(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A page of assistants is a list of the same response schema."""
        service.list = AsyncMock(return_value=[_hca(), _hca("hca-2")])
        response = client.get("/api/v1/hcas?page=1&size=50")
        assert response.status_code == 200
        assert [entry["id"] for entry in response.json()] == ["hca-1", "hca-2"]

    def test_an_unknown_assistant_answers_404(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The service's own exception is translated by the app-wide handler."""
        service.get = AsyncMock(side_effect=MTHcaNotFound("No assistant 'x' exists."))
        response = client.get("/api/v1/hcas/x")
        assert response.status_code == 404
        assert response.json()["detail"] == "No assistant 'x' exists."

    def test_deleting_an_assistant_with_an_account_answers_409(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A sign-in account still pointing at them blocks the removal."""
        service.delete = AsyncMock(
            side_effect=MTHcaHasAccount("Assistant 'hca-1' still has an account.")
        )
        response = client.delete("/api/v1/hcas/hca-1")
        assert response.status_code == 409

    def test_deleting_an_assistant_with_no_future_visit_answers_204(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """Nothing to replan means nothing is queued, and no body comes back.

        Notes:
            Queueing a run that would place the same visits in the same slots
            costs thirty seconds of a worker and makes the calendar flicker for
            no reason.
        """
        service.delete = AsyncMock(return_value=None)
        response = client.delete("/api/v1/hcas/hca-1")
        assert response.status_code == 204
        assert response.content == b""

    def test_deleting_an_assistant_with_future_visits_answers_202(
        self, client: TestClient, service: MagicMock, plannings: AsyncMock
    ) -> None:
        """A replan is queued over exactly the days they were due to work.

        Notes:
            The span is measured **before** the delete, because their visits go
            with them: asking afterwards would find nothing and replan nothing,
            leaving the rest of the workforce with a calendar built around
            somebody who has gone.
        """
        service.delete = AsyncMock(return_value=None)
        plannings.future_period_for_hca.return_value = (
            date(2026, 8, 10),
            date(2026, 8, 14),
        )
        plannings.future_teams_for_hca.return_value = ["team-1"]
        plannings.queue_replan.return_value = [
            PlanningRun(
                company_id="company-1",
                team_id="team-1",
                id="run-1",
                status=PlanningRunStatus.PENDING,
                requested_by="user-1",
                period_start=date(2026, 8, 10),
                period_end=date(2026, 8, 14),
            )
        ]

        response = client.delete("/api/v1/hcas/hca-1")

        assert response.status_code == 202
        # A list, because a departing assistant may have held work with more
        # than one team and a run rebuilds one team's week.
        assert [run["id"] for run in response.json()] == ["run-1"]
        assert plannings.queue_replan.await_args.kwargs["period"] == (
            date(2026, 8, 10),
            date(2026, 8, 14),
        )
        assert plannings.queue_replan.await_args.kwargs["team_ids"] == ["team-1"]

    def test_the_period_is_measured_before_the_assistant_goes(
        self, client: TestClient, service: MagicMock, plannings: AsyncMock
    ) -> None:
        """Their visits go with them, so the span must be read first.

        Notes:
            **This ordering is the whole feature.** Reading the span after the
            delete finds nothing, queues nothing, and leaves every customer
            they were due to visit unvisited with a green run record saying so.
        """
        order: List[str] = []
        plannings.future_period_for_hca.side_effect = lambda hca_id: (
            order.append("measured") or None
        )
        service.delete = AsyncMock(
            side_effect=lambda *args, **kwargs: order.append("deleted")
        )

        client.delete("/api/v1/hcas/hca-1")

        assert order == ["measured", "deleted"]

    def test_the_employment_change_reaches_the_service(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """All **three** editable fields are passed through, positionally.

        Notes:
            This test existed and unpacked three arguments — the identifier,
            the contract and the certifications — while the payload carried
            four things and the service took four. It pinned the wrong shape,
            so the endpoint could drop ``field_employee`` and stay green.
            Unpacking the whole call is the point: a fourth argument that
            stops being passed fails here rather than in a planning run.
        """
        service.set_employment = AsyncMock(return_value=_hca())
        response = client.patch(
            "/api/v1/hcas/hca-1/employment",
            json={
                "contract_type": "cdd",
                "certifications": [{"name": "DEAS", "issuer": "Ministère"}],
                "field_employee": True,
            },
        )
        assert response.status_code == 200
        hca_id, contract_type, certifications, field_employee = (
            service.set_employment.await_args.args
        )
        assert hca_id == "hca-1"
        assert contract_type is ContractType.CDD
        assert [entry.name for entry in certifications] == ["DEAS"]
        assert field_employee is True

    def test_taking_somebody_off_the_rounds_reaches_the_service(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """``false`` is the value that never used to arrive.

        Notes:
            **This is the regression test.** The endpoint dropped the field and
            the repository defaulted it to ``True``, so switching somebody off
            the rounds answered 200 with the record unchanged — and an
            unrelated contract edit silently put back anybody who had been
            switched off. Neither surfaces until a run schedules a person who
            should not have been on it.
        """
        service.set_employment = AsyncMock(return_value=_hca())

        client.patch(
            "/api/v1/hcas/hca-1/employment",
            json={
                "contract_type": "cdi",
                "certifications": [],
                "field_employee": False,
            },
        )

        assert service.set_employment.await_args.args[3] is False


class TestAvailabilityEndpoints:
    """Tests for the absence endpoints."""

    def test_listing_absences_passes_the_caller_to_the_service(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The caller is what lets the service refuse a colleague's diary.

        Notes:
            ``list_availability(hca_id, caller, start, end)`` — the caller is
            positional and second. An endpoint calling it without them raises a
            ``TypeError`` at request time, which is a 500 rather than a 403.
        """
        slots: List[AvailabilitySlot] = [
            AvailabilitySlot(
                id="slot-1",
                hca_id="hca-1",
                start_date=date(2026, 8, 10),
                end_date=date(2026, 8, 20),
                kind=AvailabilityKind.HOLIDAY,
            )
        ]
        service.list_availability = AsyncMock(return_value=slots)
        response = client.get("/api/v1/hcas/hca-1/availability")
        assert response.status_code == 200
        assert service.list_availability.await_args.args[0] == "hca-1"
        assert isinstance(service.list_availability.await_args.args[1], User)

    def test_filing_an_absence_answers_201(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A filed absence comes back as stored."""
        stored = AvailabilitySlot(
            id="slot-1",
            hca_id="hca-1",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 20),
            kind=AvailabilityKind.HOLIDAY,
        )
        service.add_availability = AsyncMock(return_value=stored)
        payload: Dict[str, str] = {
            "hca_id": "hca-1",
            "start_date": "2026-08-10",
            "end_date": "2026-08-20",
            "kind": "holiday",
        }
        response = client.post("/api/v1/hcas/hca-1/availability", json=payload)
        assert response.status_code == 201
        assert response.json()["id"] == "slot-1"

    def test_withdrawing_an_absence_answers_204(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A withdrawal carries no body."""
        service.remove_availability = AsyncMock(return_value=None)
        response = client.delete("/api/v1/hcas/hca-1/availability/slot-1")
        assert response.status_code == 204

    def test_setting_the_working_week_answers_the_assistant(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The whole assistant comes back, carrying the new week.

        Notes:
            Returning the record rather than just the week saves a client that
            has changed it a second call to redisplay, and keeps the working
            week and the absences on one shape in both directions.
        """
        service.set_working_days = AsyncMock(
            return_value=_hca().model_copy(
                update={"working_weekdays": [Weekday.MONDAY, Weekday.FRIDAY]}
            )
        )
        response = client.put(
            "/api/v1/hcas/hca-1/working-days",
            json={"working_weekdays": ["monday", "friday"]},
        )

        assert response.status_code == 200
        assert response.json()["working_weekdays"] == ["monday", "friday"]

    def test_setting_the_working_week_passes_the_caller_to_the_service(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The caller is what lets the service refuse a colleague's rota.

        Notes:
            ``set_working_days(hca_id, working_weekdays, caller)`` — the caller
            is positional and third. An endpoint calling it without them raises
            a ``TypeError`` at request time, which is a 500 rather than a 403.
        """
        service.set_working_days = AsyncMock(return_value=_hca())
        client.put(
            "/api/v1/hcas/hca-1/working-days",
            json={"working_weekdays": ["monday"]},
        )

        assert service.set_working_days.await_args.args[0] == "hca-1"
        assert service.set_working_days.await_args.args[1] == [Weekday.MONDAY]
        assert isinstance(service.set_working_days.await_args.args[2], User)

    def test_the_assistant_is_taken_from_the_path_not_the_payload(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A body naming a colleague files against the addressed assistant.

        Notes:
            The payload carries no assistant identifier at all, so there is
            nothing for a caller to put a colleague's in. This asserts the
            extra field is ignored rather than honoured — if the schema ever
            gained one, the ownership check would be guarding the wrong person.
        """
        service.set_working_days = AsyncMock(return_value=_hca())
        response = client.put(
            "/api/v1/hcas/hca-1/working-days",
            json={"hca_id": "hca-9", "working_weekdays": ["monday"]},
        )

        assert response.status_code == 200
        assert service.set_working_days.await_args.args[0] == "hca-1"

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"working_weekdays": []}, id="every box cleared"),
            pytest.param({"working_weekdays": ["funday"]}, id="not a weekday"),
            pytest.param({}, id="no week at all"),
        ],
    )
    def test_an_unusable_week_answers_422(
        self, client: TestClient, service: MagicMock, payload: Dict[str, ModelInput]
    ) -> None:
        """A week nobody could work is refused before it reaches the service.

        Args:
            client (TestClient): The client under test.
            service (MagicMock): The service double.
            payload (Dict[str, ModelInput]): The rejected body.
        """
        service.set_working_days = AsyncMock(return_value=_hca())
        response = client.put("/api/v1/hcas/hca-1/working-days", json=payload)

        assert response.status_code == 422
        service.set_working_days.assert_not_called()

    def test_a_refused_working_week_answers_404_for_a_ghost(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A week set on nobody is a 404, mapped by the handler table."""
        service.set_working_days = AsyncMock(
            side_effect=MTHcaNotFound("No assistant 'ghost' exists.")
        )
        response = client.put(
            "/api/v1/hcas/ghost/working-days",
            json={"working_weekdays": ["monday"]},
        )

        assert response.status_code == 404
