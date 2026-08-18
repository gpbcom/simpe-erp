from __future__ import annotations

# Standard library imports
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_current_user,
    get_event_publisher,
    get_hca_service,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.hcas.skills import router as hca_skills_router
from api.v1.me.me import router as me_router
from models.auth.user import User
from models.enums import EventRoutingKey, UserRole
from models.people.hca.skill import Skill
from service.hcas.exceptions import MTHcaForbidden, MTSkillNotFound


def _user(role: UserRole = UserRole.HCA, hca_id: Optional[str] = "hca-1") -> User:
    """Build the account the request is authenticated as.

    Args:
        role (UserRole): The role it holds.
        hca_id (Optional[str]): The assistant record it is bound to.

    Returns:
        User: The caller.
    """
    return User(
        company_id="company-1",
        id="user-1",
        email="luc@example.com",
        full_name="Luc Martin",
        role=role,
        hca_id=hca_id,
    )


class RecordingPublisher:
    """A publisher that remembers rather than reaching a broker.

    Attributes:
        published (List[Tuple[EventRoutingKey, str, dict]]): Every message, in
            order.
    """

    def __init__(self) -> None:
        """Initialize the recorder."""
        self.published: List[Tuple[EventRoutingKey, str, dict]] = []

    async def publish(
        self, routing_key: EventRoutingKey, company_id: str, payload: dict
    ) -> bool:
        """Record a message instead of sending it.

        Args:
            routing_key (EventRoutingKey): The topic.
            company_id (str): The agency it is scoped to.
            payload (dict): The body.

        Returns:
            bool: Always ``True``.
        """
        self.published.append((routing_key, company_id, payload))
        return True


@pytest.fixture
def hcas() -> AsyncMock:
    """Return a stubbed assistant service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.add_skill.return_value = Skill(
        id="skill-1", name="Leve-personne", code="LEVE-PERSONNE"
    )
    stub.remove_skill.return_value = None
    return stub


@pytest.fixture
def publisher() -> RecordingPublisher:
    """Return a publisher that records what the route announces.

    Returns:
        RecordingPublisher: The recorder.
    """
    return RecordingPublisher()


def _client(caller: User, hcas: AsyncMock, publisher: RecordingPublisher) -> TestClient:
    """Build a client over both skill-declaration routers.

    Args:
        caller (User): The account the request is made as.
        hcas (AsyncMock): The assistant service double.
        publisher (RecordingPublisher): The publisher double.

    Returns:
        TestClient: A client with the guards and services overridden.
    """
    app = FastAPI()
    app.include_router(me_router)
    app.include_router(hca_skills_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_current_user] = lambda: caller
    app.dependency_overrides[get_manager_user] = lambda: caller
    app.dependency_overrides[get_hca_service] = lambda: hcas
    app.dependency_overrides[get_event_publisher] = lambda: publisher
    return TestClient(app)


class TestDeclaringMySkill:
    """Tests for an assistant declaring a skill about themselves."""

    def test_a_declaration_answers_201(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """The stored skill comes back with the identifier a delete needs."""
        client = _client(_user(), hcas, publisher)

        response = client.post(
            "/api/v1/me/hca/skills",
            json={"name": "Leve-personne", "code": "LEVE-PERSONNE"},
        )

        assert response.status_code == 201
        assert response.json()["id"] == "skill-1"

    def test_the_owner_comes_from_the_credential(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """**This is the permission.**

        Notes:
            The payload has no ``hca_id`` to send, so there is nothing to
            ignore — a declaration cannot be filed against a colleague.
        """
        client = _client(_user(), hcas, publisher)

        client.post(
            "/api/v1/me/hca/skills",
            json={"name": "x", "code": "X", "hca_id": "hca-2"},
        )

        assert hcas.add_skill.await_args.args[0] == "hca-1"

    def test_the_identifier_cannot_be_chosen_by_the_caller(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """One chosen by a caller would be one a caller could collide with."""
        client = _client(_user(), hcas, publisher)

        client.post("/api/v1/me/hca/skills", json={"name": "x", "id": "chosen"})

        assert hcas.add_skill.await_args.args[1].id is None

    def test_the_supervisors_are_announced(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """A declaration needs no approval, so the agency is told instead.

        Notes:
            Somebody adding a skill silently widens what they can be sent to.
            The notification is what leaves a supervisor able to challenge it
            before the next run acts on it.
        """
        client = _client(_user(), hcas, publisher)

        client.post("/api/v1/me/hca/skills", json={"name": "x", "code": "X"})

        assert len(publisher.published) == 1
        routing_key, company_id, payload = publisher.published[0]
        assert routing_key is EventRoutingKey.SKILL_ADDED
        assert company_id == "company-1"
        assert payload["hca_id"] == "hca-1"
        assert payload["skill_code"] == "LEVE-PERSONNE"

    def test_nothing_is_announced_when_the_write_failed(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """A notification about a skill nobody holds is worse than none.

        Notes:
            The publish sits after the service call for exactly this reason. A
            message sent from inside the service would fire on a write a later
            failure could roll back.
        """
        hcas.add_skill.side_effect = MTHcaForbidden("not yours")
        client = _client(_user(), hcas, publisher)

        response = client.post("/api/v1/me/hca/skills", json={"name": "x"})

        assert response.status_code == 403
        assert publisher.published == []

    def test_an_account_with_no_assistant_record_is_refused(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """A manager has no record to declare a skill on."""
        client = _client(_user(UserRole.MANAGER, hca_id=None), hcas, publisher)

        response = client.post("/api/v1/me/hca/skills", json={"name": "x"})

        assert response.status_code == 403
        hcas.add_skill.assert_not_awaited()

    def test_a_nameless_declaration_answers_422(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """A declaration with no name is not a record anybody keeps."""
        client = _client(_user(), hcas, publisher)

        assert (
            client.post("/api/v1/me/hca/skills", json={"name": "  "}).status_code == 422
        )

    def test_a_malformed_code_answers_422(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """A malformed code would match nothing and qualify nobody."""
        client = _client(_user(), hcas, publisher)

        response = client.post(
            "/api/v1/me/hca/skills", json={"name": "x", "code": "LEVÉ"}
        )

        assert response.status_code == 422


class TestWithdrawingMySkill:
    """Tests for an assistant withdrawing one of their own skills."""

    def test_a_withdrawal_answers_204(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """Its owner may take back what they said about themselves."""
        client = _client(_user(), hcas, publisher)

        assert client.delete("/api/v1/me/hca/skills/skill-1").status_code == 204

    def test_the_owner_comes_from_the_credential(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """Knowing a skill id is not enough to strip a colleague of one."""
        client = _client(_user(), hcas, publisher)

        client.delete("/api/v1/me/hca/skills/skill-1")

        assert hcas.remove_skill.await_args.args[:2] == ("hca-1", "skill-1")

    def test_a_skill_that_is_not_the_caller_s_answers_404(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """The same 404 whether it is absent or simply not theirs.

        Notes:
            Distinguishing the two would let somebody discover which
            identifiers are real by trying them.
        """
        hcas.remove_skill.side_effect = MTSkillNotFound("no such skill")
        client = _client(_user(), hcas, publisher)

        assert client.delete("/api/v1/me/hca/skills/nope").status_code == 404

    def test_a_withdrawal_announces_nothing(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """An addition widens what somebody may be sent to. A removal narrows it.

        Notes:
            A badge for every correction of a typed name would train
            supervisors to ignore the ones that matter.
        """
        client = _client(_user(), hcas, publisher)

        client.delete("/api/v1/me/hca/skills/skill-1")

        assert publisher.published == []


class TestSupervisorWithdrawal:
    """Tests for a manager or an administrator removing anybody's skill."""

    def test_a_supervisor_may_withdraw_a_skill(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """The correction a declaration needing no approval depends on."""
        client = _client(_user(UserRole.MANAGER, hca_id=None), hcas, publisher)

        response = client.delete("/api/v1/hcas/hca-2/skills/skill-1")

        assert response.status_code == 204
        assert hcas.remove_skill.await_args.args[:2] == ("hca-2", "skill-1")

    def test_an_absent_skill_answers_404(
        self, hcas: AsyncMock, publisher: RecordingPublisher
    ) -> None:
        """A skill that is not that assistant's is a 404."""
        hcas.remove_skill.side_effect = MTSkillNotFound("no such skill")
        client = _client(_user(UserRole.MANAGER, hca_id=None), hcas, publisher)

        assert client.delete("/api/v1/hcas/hca-2/skills/nope").status_code == 404

    def test_there_is_no_supervisor_route_to_declare_one(self) -> None:
        """Adding is self-service only, and that is written as a routing table.

        Notes:
            A skill is a claim about what somebody can do. A manager may
            withdraw one they believe is wrong. Nothing lets them put a claim
            in somebody else's mouth.
        """
        assert [sorted(route.methods) for route in hca_skills_router.routes] == [
            ["DELETE"]
        ] * len(hca_skills_router.routes)
