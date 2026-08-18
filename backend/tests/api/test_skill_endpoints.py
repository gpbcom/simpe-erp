from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_current_user,
    get_manager_user,
    get_skill_type_service,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.skills.skills import router as skills_router
from models.auth.user import User
from models.catalog.skill_type import SkillType
from models.enums import UserRole
from service.skills.exceptions import (
    MTSkillTypeAlreadyExists,
    MTSkillTypeInUse,
    MTSkillTypeNotFound,
)


def _entry(code: str = "TOILETTE") -> SkillType:
    """Build a catalogue entry.

    Args:
        code (str): The code to assign.

    Returns:
        SkillType: The entry.
    """
    return SkillType(id=f"type-{code.lower()}", code=code, label=f"Competence {code}")


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
    """Return a client over the skills router alone.

    Args:
        service (AsyncMock): The stubbed catalogue service.

    Returns:
        TestClient: The client, with the service and both guards replaced.
    """
    app = FastAPI()
    app.include_router(skills_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_skill_type_service] = lambda: service
    app.dependency_overrides[get_manager_user] = lambda: _user()
    app.dependency_overrides[get_current_user] = lambda: _user(UserRole.HCA)
    return TestClient(app)


class TestSkillCatalogueEndpoints:
    """Tests for the skill-catalogue routes."""

    def test_listing_is_open_to_any_signed_in_caller(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """This is the list an assistant picks their own skills from.

        Notes:
            It matters more here than for the certification catalogue: an
            assistant declares their own skills, so a screen that could not
            read this would leave them typing a code from memory and matching
            nothing.
        """
        response = client.get("/api/v1/skills")

        assert response.status_code == 200
        assert response.json()[0]["code"] == "TOILETTE"

    def test_retired_entries_are_hidden_unless_asked(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """The picker offers only what may still be declared."""
        client.get("/api/v1/skills?include_inactive=true")

        assert service.list.await_args.kwargs["include_inactive"] is True

    def test_creating_an_entry_answers_201(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A stored entry comes back with its identifier."""
        response = client.post(
            "/api/v1/skills",
            json={"code": "ARABE", "label": "Arabe parle"},
        )

        assert response.status_code == 201
        assert response.json()["id"] == "type-toilette"

    def test_a_duplicate_code_answers_409(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """The unique index reaches the client as a conflict, not a 500."""
        service.create.side_effect = MTSkillTypeAlreadyExists("taken")

        response = client.post(
            "/api/v1/skills", json={"code": "TOILETTE", "label": "Toilette"}
        )

        assert response.status_code == 409

    def test_a_malformed_code_answers_422(self, client: TestClient) -> None:
        """The model's own validator is translated by the app-wide handler."""
        response = client.post("/api/v1/skills", json={"code": "LEVÉ", "label": "Leve"})

        assert response.status_code == 422

    def test_an_edit_sends_only_what_changed(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A label change must not reset the description."""
        client.patch("/api/v1/skills/type-toilette", json={"label": "Renamed"})

        assert service.update.await_args.kwargs["label"] == "Renamed"
        assert service.update.await_args.kwargs["description"] is None
        assert service.update.await_args.kwargs["is_active"] is None

    def test_the_code_cannot_be_edited(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A code in the payload never reaches the service.

        Notes:
            **This test is the rule.** Renaming a code would un-skill every
            assistant who declared it on the next planning run. Pydantic
            ignores the unknown field, so this passes rather than raising —
            what matters is that the value cannot travel.
        """
        client.patch("/api/v1/skills/type-toilette", json={"code": "OTHER"})

        assert "code" not in service.update.await_args.kwargs

    def test_editing_an_absent_entry_answers_404(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A missing entry is a 404, not a silent success."""
        service.update.side_effect = MTSkillTypeNotFound("no such entry")

        response = client.patch("/api/v1/skills/ghost", json={"label": "Renamed"})

        assert response.status_code == 404

    def test_deleting_an_unreferenced_entry_answers_204(
        self, client: TestClient
    ) -> None:
        """An entry added by mistake this morning goes cleanly."""
        assert client.delete("/api/v1/skills/type-toilette").status_code == 204

    def test_deleting_a_referenced_entry_answers_409(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """No foreign key protects those references, so the check is the rule."""
        service.delete.side_effect = MTSkillTypeInUse("still in use")

        response = client.delete("/api/v1/skills/type-toilette")

        assert response.status_code == 409

    def test_deleting_an_absent_entry_answers_404(
        self, client: TestClient, service: AsyncMock
    ) -> None:
        """A missing entry is a 404."""
        service.delete.side_effect = MTSkillTypeNotFound("no such entry")

        assert client.delete("/api/v1/skills/ghost").status_code == 404
