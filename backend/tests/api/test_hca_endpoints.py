from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import get_current_user, get_hca_service, get_manager_user
from api.main import app
from models.auth.user import User
from models.enums import AvailabilityKind, ContractType, UserRole
from models.people.availability_slot import AvailabilitySlot
from models.people.hca import Hca
from service.hcas.exceptions import MTHcaHasAccount, MTHcaNotFound
from service.hcas.hcas import HcaService


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
def client(service: MagicMock) -> TestClient:
    """Return a client over the production application.

    Args:
        service (MagicMock): The stubbed assistant service.

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
            "driving_license",
            "photo_url",
            "availability",
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

    def test_deleting_an_assistant_answers_204(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A removal carries no body."""
        service.delete = AsyncMock(return_value=None)
        response = client.delete("/api/v1/hcas/hca-1")
        assert response.status_code == 204
        assert response.content == b""

    def test_the_employment_change_reaches_the_service(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The two editable fields are passed through as the service expects.

        Notes:
            The service signature is ``set_employment(hca_id, contract_type,
            certifications)``; this pins the endpoint to it, which is the
            arrangement that broke silently before.
        """
        service.set_employment = AsyncMock(return_value=_hca())
        response = client.patch(
            "/api/v1/hcas/hca-1/employment",
            json={
                "contract_type": "cdd",
                "certifications": [{"name": "DEAS", "issuer": "Ministère"}],
            },
        )
        assert response.status_code == 200
        hca_id, contract_type, certifications = service.set_employment.await_args.args
        assert hca_id == "hca-1"
        assert contract_type is ContractType.CDD
        assert [entry.name for entry in certifications] == ["DEAS"]


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
