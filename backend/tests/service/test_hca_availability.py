from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List, Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.enums import AvailabilityKind, ContractType, UserRole, Weekday
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.hca import Hca
from service.hcas.exceptions import MTHcaForbidden, MTHcaNotFound
from service.hcas.hcas import HcaService

MONDAY = date(2026, 8, 3)
SUNDAY = date(2026, 8, 9)


def _user(role: UserRole, hca_id: Optional[str] = None) -> User:
    """Build an authenticated account.

    Args:
        role (UserRole): What the account may do.
        hca_id (Optional[str]): The assistant record it is bound to, if any.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name=f"Test {role.value.title()}",
        role=role,
        hca_id=hca_id,
    )


def _slot(hca_id: str = "hca-1") -> AvailabilitySlot:
    """Build a one-day absence.

    Args:
        hca_id (str): The assistant it belongs to.

    Returns:
        AvailabilitySlot: The absence.
    """
    return AvailabilitySlot(
        id="slot-1",
        hca_id=hca_id,
        start_date=SUNDAY,
        end_date=SUNDAY,
        kind=AvailabilityKind.DAY_OFF,
    )


def _hca_working(working_weekdays: List[Weekday]) -> Hca:
    """Build an assistant working a given week.

    Args:
        working_weekdays (List[Weekday]): The days they work.

    Returns:
        Hca: The assistant, as the repository would hand them back.
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
        },
        contract_type=ContractType.CDI,
        working_weekdays=working_weekdays,
    )


@pytest.fixture
def hcas() -> AsyncMock:
    """Return a stand-in assistant repository.

    Returns:
        AsyncMock: The repository double, accepting every write.
    """
    repository = AsyncMock()
    repository.add_availability.return_value = _slot()
    repository.remove_availability.return_value = True
    repository.list_availability.return_value = [_slot()]
    return repository


@pytest.fixture
def service(hcas: AsyncMock) -> HcaService:
    """Return an assistant service over a stand-in repository.

    Args:
        hcas (AsyncMock): The repository double.

    Returns:
        HcaService: The service under test.
    """
    return HcaService(hcas=hcas, photos=AsyncMock())


class TestAvailabilityConfidentiality:
    """Tests for the rule that an assistant manages only their own diary."""

    # ------------------------------------------------------------------ #
    #  An assistant and their own record
    # ------------------------------------------------------------------ #

    async def test_an_assistant_files_their_own_absence(
        self, service: HcaService
    ) -> None:
        """The ordinary case works: this is how availability is declared."""
        stored = await service.add_availability(
            "hca-1", _slot(), _user(UserRole.HCA, "hca-1")
        )

        assert stored.kind is AvailabilityKind.DAY_OFF

    async def test_an_assistant_reads_their_own_absences(
        self, service: HcaService
    ) -> None:
        """An assistant can see what they declared."""
        slots = await service.list_availability(
            "hca-1", _user(UserRole.HCA, "hca-1"), start=MONDAY, end=SUNDAY
        )

        assert len(slots) == 1

    async def test_an_assistant_withdraws_their_own_absence(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """Withdrawing one's own absence is allowed."""
        await service.remove_availability(
            "hca-1", "slot-1", _user(UserRole.HCA, "hca-1")
        )

        hcas.remove_availability.assert_awaited_once_with("hca-1", "slot-1")

    # ------------------------------------------------------------------ #
    #  An assistant and somebody else's
    # ------------------------------------------------------------------ #

    async def test_an_assistant_cannot_book_a_colleague_off_work(
        self, service: HcaService
    ) -> None:
        """Filing against a colleague is refused.

        Notes:
            **This is the test the rule rests on.** A route guard proves only
            that the caller is an assistant; nothing at the routing layer stops
            assistant A putting assistant B's identifier in the path, and an
            absence filed against B takes them off the rota.
        """
        with pytest.raises(MTHcaForbidden):
            await service.add_availability(
                "hca-2", _slot("hca-2"), _user(UserRole.HCA, "hca-1")
            )

    async def test_a_refused_filing_never_reaches_the_store(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """The check happens before the write, not after it."""
        with pytest.raises(MTHcaForbidden):
            await service.add_availability(
                "hca-2", _slot("hca-2"), _user(UserRole.HCA, "hca-1")
            )

        hcas.add_availability.assert_not_called()

    async def test_an_assistant_cannot_read_a_colleagues_absences(
        self, service: HcaService
    ) -> None:
        """An absence carries a reason, so reading one is a disclosure.

        Notes:
            Sick leave and training are in the same list as a plain day off;
            letting a colleague read it would leak why somebody was away.
        """
        with pytest.raises(MTHcaForbidden):
            await service.list_availability("hca-2", _user(UserRole.HCA, "hca-1"))

    async def test_an_assistant_cannot_withdraw_a_colleagues_absence(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """Knowing a slot identifier is not enough to cancel somebody's leave."""
        with pytest.raises(MTHcaForbidden):
            await service.remove_availability(
                "hca-2", "slot-1", _user(UserRole.HCA, "hca-1")
            )

        hcas.remove_availability.assert_not_called()

    async def test_an_unbound_assistant_account_is_refused(
        self, service: HcaService
    ) -> None:
        """An assistant account with no record manages nobody's diary.

        Notes:
            :class:`User` refuses to build such an account, so it is forced
            into existence here to prove the service does not read "unbound" as
            "unrestricted".
        """
        unbound = User.model_construct(
            id="user-hca",
            email="hca@example.com",
            full_name="Test Hca",
            role=UserRole.HCA,
            hca_id=None,
        )

        with pytest.raises(MTHcaForbidden):
            await service.add_availability("hca-1", _slot(), unbound)

    # ------------------------------------------------------------------ #
    #  Supervisors
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(UserRole.MANAGER, id="Allowed - manager"),
            pytest.param(UserRole.ADMIN, id="Allowed - admin"),
        ],
    )
    async def test_a_manager_may_file_for_anybody(
        self, service: HcaService, role: UserRole
    ) -> None:
        """Filing for somebody who telephoned in sick is the job.

        Args:
            service (HcaService): The service under test.
            role (UserRole): The supervising role to check.
        """
        assert await service.add_availability("hca-1", _slot(), _user(role))

    async def test_a_manager_may_read_any_absences(self, service: HcaService) -> None:
        """Supervision requires seeing who is off."""
        assert await service.list_availability("hca-9", _user(UserRole.MANAGER))


class TestWorkingDaysConfidentiality:
    """Tests for who may set an assistant's recurring working week."""

    async def test_an_assistant_sets_their_own_working_week(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """The declaration is the assistant's own to make.

        Args:
            service (HcaService): The service under test.
            hcas (AsyncMock): The repository double.
        """
        hcas.set_working_weekdays.return_value = _hca_working(
            [Weekday.MONDAY, Weekday.TUESDAY]
        )
        updated = await service.set_working_days(
            "hca-1",
            [Weekday.MONDAY, Weekday.TUESDAY],
            _user(UserRole.HCA, hca_id="hca-1"),
        )

        assert updated.working_weekdays == [Weekday.MONDAY, Weekday.TUESDAY]

    async def test_an_assistant_cannot_set_a_colleagues_working_week(
        self, service: HcaService
    ) -> None:
        """A week filed against a colleague would take them off their rounds.

        Notes:
            Nothing at the routing layer stops assistant A putting assistant
            B's identifier in the path; only the service can compare the two.
        """
        with pytest.raises(MTHcaForbidden):
            await service.set_working_days(
                "hca-9",
                [Weekday.MONDAY],
                _user(UserRole.HCA, hca_id="hca-1"),
            )

    async def test_a_refused_change_never_reaches_the_store(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """The ownership check runs before the write, not after it.

        Args:
            service (HcaService): The service under test.
            hcas (AsyncMock): The repository double.
        """
        with pytest.raises(MTHcaForbidden):
            await service.set_working_days(
                "hca-9",
                [Weekday.MONDAY],
                _user(UserRole.HCA, hca_id="hca-1"),
            )

        hcas.set_working_weekdays.assert_not_called()

    @pytest.mark.parametrize(
        "role",
        [
            pytest.param(UserRole.MANAGER, id="Allowed - manager"),
            pytest.param(UserRole.ADMIN, id="Allowed - admin"),
        ],
    )
    async def test_a_supervisor_may_set_anybodys_working_week(
        self, service: HcaService, hcas: AsyncMock, role: UserRole
    ) -> None:
        """Recording that somebody has dropped to four days is the job.

        Args:
            service (HcaService): The service under test.
            hcas (AsyncMock): The repository double.
            role (UserRole): The supervising role to check.
        """
        hcas.set_working_weekdays.return_value = _hca_working([Weekday.FRIDAY])

        assert await service.set_working_days("hca-9", [Weekday.FRIDAY], _user(role))

    async def test_an_absent_assistant_is_reported(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """A week set on nobody is a 404, not a silent success.

        Args:
            service (HcaService): The service under test.
            hcas (AsyncMock): The repository double.
        """
        hcas.set_working_weekdays.return_value = None

        with pytest.raises(MTHcaNotFound):
            await service.set_working_days(
                "ghost", [Weekday.MONDAY], _user(UserRole.ADMIN)
            )
