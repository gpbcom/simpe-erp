from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_certification_type_service,
    get_current_user,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.certifications.certifications import router as certifications_router
from models.auth.user import User
from models.catalog.certification_type import CertificationType
from models.enums import UserRole
from service.certifications.exceptions import (
    MTCertificationTypeAlreadyExists,
    MTCertificationTypeInUse,
    MTCertificationTypeNotFound,
)


def _entry(code: str = "DEAES") -> CertificationType:
    """Build a catalogue entry.

    Args:
        code (str): The code to assign.

    Returns:
        CertificationType: The entry.
    """
    return CertificationType(
        id=f"type-{code.lower()}", code=code, label=f"Diplome {code}"
    )


def _user(role: UserRole = UserRole.MANAGER) -> User:
    """Build the account the request is authenticated as.

    Args:
        role (UserRole): The role it holds.

    Returns:
        User: The caller.
    """
    return User(
        company_id="company-1",
        id="user-1",
        email="manager@example.com",
        full_name="Manager",
        role=role,
        hca_id="hca-1" if role is UserRole.HCA else None,
    )


@pytest.fixture
def service() -> AsyncMock:
    """Return a stubbed catalogue service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.list.return_value = [_entry()]
    stub.create.return_value = _entry()
    stub.update.return_value = _entry()
    stub.delete.return_value = None
    return stub


@pytest.fixture
def client(service: AsyncMock) -> TestClient:
    """Return a client over the certifications router alone.

    Args:
        service (AsyncMock): The stubbed catalogue service.

    Returns:
        TestClient: The client, with the service and both guards replaced.
    """
    app = FastAPI()
    app.include_router(certifications_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_certification_type_service] = lambda: service
    app.dependency_overrides[get_manager_user] = lambda: _user()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.HCA)
    return TestClient(app)


class TestCertificationCatalogueEndpoints:
    """Tests for the certification-catalogue routes."""

    def test_listing_is_open_to_any_signed_in_caller(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """An assistant's own screen names their qualifications by label.

        Notes:
            The read is guarded on ``get_current_user`` rather than on a
            manager, because a screen that could not read this would have to
            print ``DEAES`` at somebody and hope.
        """
        response = client.get("/api/v1/certifications")

        assert response.status_code == 200
        assert response.json()[0]["code"] == "DEAES"

    def test_retired_entries_are_hidden_unless_asked_for(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A screen offering a requirement offers only what may be required."""
        client.get("/api/v1/certifications?include_inactive=true")

        assert service.list.await_args.kwargs["include_inactive"] is True

    def test_creating_an_entry_answers_201(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A stored entry comes back with its identifier."""
        response = client.post(
            "/api/v1/certifications",
            json={"code": "SST", "label": "Sauveteur Secouriste du Travail"},
        )

        assert response.status_code == 201
        assert response.json()["id"] == "type-deaes"

    def test_a_duplicate_code_answers_409(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """The unique index reaches the client as a conflict, not a 500."""
        service.create.side_effect = MTCertificationTypeAlreadyExists("taken")

        response = client.post(
            "/api/v1/certifications", json={"code": "DEAES", "label": "Diplome"}
        )

        assert response.status_code == 409

    def test_a_malformed_code_answers_422(self, client: TestClient) -> None:
        """The model's own validator is translated by the app-wide handler.

        Notes:
            An accented code is refused because the code travels into CSV
            exports and URLs, where an accent is escaped differently by every
            consumer.
        """
        response = client.post(
            "/api/v1/certifications", json={"code": "DÉAES", "label": "Diplome"}
        )

        assert response.status_code == 422

    def test_an_edit_sends_only_what_changed(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A label change must not reset the description.

        Notes:
            The route reads ``exclude_unset``, so an omitted field arrives as
            ``None`` and the service leaves it alone.
        """
        client.patch("/api/v1/certifications/type-deaes", json={"label": "Renamed"})

        assert service.update.await_args.kwargs["label"] == "Renamed"
        assert service.update.await_args.kwargs["description"] is None
        assert service.update.await_args.kwargs["is_active"] is None

    def test_the_code_cannot_be_edited(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A code in the payload never reaches the service.

        Notes:
            **This test is the rule.** Renaming a code would disqualify every
            assistant holding it on the next planning run. Pydantic ignores the
            unknown field, so this passes rather than raising — what matters is
            that the value cannot travel.
        """
        client.patch("/api/v1/certifications/type-deaes", json={"code": "OTHER"})

        assert "code" not in service.update.await_args.kwargs

    def test_editing_an_absent_entry_answers_404(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A missing entry is a 404, not a silent success."""
        service.update.side_effect = MTCertificationTypeNotFound("no such entry")

        response = client.patch(
            "/api/v1/certifications/ghost", json={"label": "Renamed"}
        )

        assert response.status_code == 404

    def test_deleting_an_unreferenced_entry_answers_204(
        self, client: TestClient
    ) -> None:
        """A removal carries no body."""
        response = client.delete("/api/v1/certifications/type-deaes")

        assert response.status_code == 204
        assert response.content == b""

    def test_deleting_a_referenced_entry_answers_409(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """The check standing in for a missing foreign key reaches the client.

        Notes:
            409 rather than 403: the request is permitted and the state refuses
            it. Letting it through would leave a requirement pointing at
            nothing, which fails every planning run it touches.
        """
        service.delete.side_effect = MTCertificationTypeInUse(
            "still in use by 2 assistant(s). Retire it instead"
        )

        response = client.delete("/api/v1/certifications/type-deaes")

        assert response.status_code == 409
        assert "Retire it instead" in response.json()["detail"]
