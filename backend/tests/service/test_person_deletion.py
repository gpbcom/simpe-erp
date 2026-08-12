from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List, Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.enums import ContractType, PlanningRunStatus, UserRole
from models.people.hca import Hca
from models.planning.planning_run import PlanningRun
from service.hcas.exceptions import MTHcaHasAccount
from service.hcas.hcas import HcaService
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 10)
FRIDAY = date(2026, 8, 14)


def _hca() -> Hca:
    """Build an assistant.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        company_id="company-1",
        id="hca-1",
        first_name="Luc",
        last_name="Martin",
        phone_number="+33612345678",
        email="luc@example.com",
        address={
            "street": "1 rue A",
            "postal_code": "75001",
            "city": "Paris",
            "latitude": 48.85,
            "longitude": 2.35,
        },
        contract_type=ContractType.CDI,
    )


def _account(role: UserRole = UserRole.HCA) -> User:
    """Build the account bound to the assistant.

    Args:
        role (UserRole): The role it holds.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id="user-1",
        email="luc@example.com",
        full_name="Luc Martin",
        role=role,
        hca_id="hca-1",
    )


def _caller() -> User:
    """Build the manager asking for the deletion.

    Returns:
        User: The caller.
    """
    return User(
        company_id="company-1",
        id="user-9",
        email="manager@example.com",
        full_name="Manager",
        role=UserRole.MANAGER,
    )


def _service(bound_account: Optional[User] = None) -> HcaService:
    """Build an assistant service over stand-in stores.

    Args:
        bound_account (Optional[User]): The account pointing at the assistant,
            if any.

    Returns:
        HcaService: The service under test.
    """
    hcas = AsyncMock()
    hcas.get.return_value = _hca()
    hcas.delete.return_value = True
    users = AsyncMock()
    users.get_by_hca_id.return_value = bound_account
    auth = AsyncMock()
    return HcaService(hcas=hcas, users=users, auth=auth)


def _planning_service() -> PlanningService:
    """Build a planning service over stand-in repositories.

    Returns:
        PlanningService: The service under test.
    """
    return PlanningService(
        runs=AsyncMock(),
        interventions=AsyncMock(),
        quotes=AsyncMock(),
        customers=AsyncMock(),
        hcas=AsyncMock(),
        types=AsyncMock(),
        settings=AsyncMock(),
        teams=AsyncMock(),
        config=AsyncMock(),
    )


class TestAssistantDeletionCascadesTheAccount:
    """Tests for removing an assistant and the account bound to them."""

    async def test_an_assistant_with_no_account_is_removed_alone(self) -> None:
        """The common case: a record created before anybody registered."""
        service = _service(bound_account=None)

        await service.delete("hca-1", requested_by=_caller())

        service.hcas.delete.assert_awaited_once_with("hca-1")
        service.auth.delete_account.assert_not_awaited()

    async def test_the_bound_account_goes_with_the_record(self) -> None:
        """An account naming a record that no longer exists is unusable.

        Notes:
            It cannot pass the row-level planning check and cannot be repaired
            through any screen, so leaving it behind was never an option — the
            foreign key was ``RESTRICT`` and the delete simply failed, which
            meant "everybody can be deleted" was not true of anybody who had
            ever signed in.
        """
        service = _service(bound_account=_account())

        await service.delete("hca-1", requested_by=_caller())

        service.auth.delete_account.assert_awaited_once()
        assert service.auth.delete_account.await_args.args[0] == "user-1"

    async def test_the_account_goes_before_the_record(self) -> None:
        """Ordering matters: the other way round leaves the orphan behind.

        Notes:
            Both writes share one transaction, so a refusal from the account
            service rolls the whole thing back — which is only true if the
            account is attempted first.
        """
        order: List[str] = []
        service = _service(bound_account=_account())
        service.auth.delete_account.side_effect = lambda *a, **k: order.append(
            "account"
        )
        service.hcas.delete.side_effect = lambda hca_id: (
            order.append("record") or True
        )

        await service.delete("hca-1", requested_by=_caller())

        assert order == ["account", "record"]

    async def test_the_callers_own_refusals_still_apply(self) -> None:
        """Not your own account, and never the last administrator.

        Notes:
            The refusals live on the account service and are reached through
            it rather than reimplemented here — two copies of "you may not
            delete the last administrator" is one copy too many.
        """
        service = _service(bound_account=_account(UserRole.ADMIN))
        service.auth.delete_account.side_effect = RuntimeError("last admin")

        with pytest.raises(RuntimeError):
            await service.delete("hca-1", requested_by=_caller())

        service.hcas.delete.assert_not_awaited()

    async def test_an_anonymous_deletion_is_refused(self) -> None:
        """Removing an account is guarded by rules about *the caller*.

        Notes:
            There is no safe way to apply "not your own" and "not the last
            administrator" to nobody, so a caller that cannot be identified
            gets the old behaviour: the delete is refused and says why.
        """
        service = _service(bound_account=_account())

        with pytest.raises(MTHcaHasAccount):
            await service.delete("hca-1", requested_by=None)

        service.hcas.delete.assert_not_awaited()
        service.auth.delete_account.assert_not_awaited()


class TestReplanScoping:
    """Tests for the period a deletion queues a replan over."""

    async def test_the_span_comes_from_their_remaining_visits(self) -> None:
        """Exactly the days they were due to work, and no others.

        Notes:
            Replanning a fixed window instead would either rewrite calendars
            nothing changed on or miss a visit at the edge of it. Today is
            resolved by the service rather than passed in, so every caller
            asking "what does removing this person disturb?" gets one answer.
        """
        service = _planning_service()
        service.interventions.future_period_for_hca.return_value = (MONDAY, FRIDAY)

        assert await service.future_period_for_hca("hca-1") == (MONDAY, FRIDAY)
        assert service.interventions.future_period_for_hca.await_args.args[0] == "hca-1"

    async def test_a_person_with_no_future_work_scopes_no_replan(self) -> None:
        """``None`` is the honest answer that no run is needed at all.

        Notes:
            Queueing one that would place the same visits in the same slots
            costs thirty seconds of a worker and makes the calendar flicker.
        """
        service = _planning_service()
        service.interventions.future_period_for_customer.return_value = None

        assert await service.future_period_for_customer("customer-1") is None

    async def test_a_recorded_run_is_returned_even_when_the_broker_refuses(
        self,
    ) -> None:
        """A broker that will not take the message is an error, not a failure.

        Notes:
            The run stays ``pending`` and the next worker to reach a reachable
            broker finds it. Raising instead would undo a deletion that has
            already happened, for a reason unrelated to it.
        """
        service = _planning_service()
        pending = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="user-9",
            period_start=MONDAY,
            period_end=FRIDAY,
        )
        service.runs.create.return_value = pending
        publisher = AsyncMock()
        publisher.publish.return_value = False

        queued = await service.queue_replan(
            requested_by="user-9",
            company_id="company-1",
            period=(MONDAY, FRIDAY),
            publisher=publisher,
            reason="a test",
        )

        assert queued.id == "run-1"

    async def test_the_run_is_recorded_before_it_is_queued(self) -> None:
        """A 202 must hand back an identifier that is already real.

        Notes:
            A run published first and stored second could be picked up by a
            worker before the row it names exists.
        """
        order: List[str] = []
        service = _planning_service()
        pending = PlanningRun(
            company_id="company-1",
            id="run-1",
            status=PlanningRunStatus.PENDING,
            requested_by="user-9",
            period_start=MONDAY,
            period_end=FRIDAY,
        )
        service.runs.create.side_effect = lambda run: (
            order.append("recorded") or pending
        )
        publisher = AsyncMock()
        publisher.publish.side_effect = lambda *a, **k: (order.append("queued") or True)

        await service.queue_replan(
            requested_by="user-9",
            company_id="company-1",
            period=(MONDAY, FRIDAY),
            publisher=publisher,
            reason="a test",
        )

        assert order == ["recorded", "queued"]
