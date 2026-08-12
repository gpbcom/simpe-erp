from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Dict

# Third-party imports
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.auth.user import User

# First-party imports
from models.organisation.companies.company import Company
from models.enums import AccountOrigin, HcaApplicationStatus, UserRole
from models.people.hca_application import HcaApplication
from models.settings.planning_settings import PlanningSettings
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.people.hca_application import HcaApplicationRepository
from storage.repositories.planning.planning_settings import PlanningSettingsRepository
from storage.repositories.auth.user import UserRepository
from tests.annotations import ModelInput

HASH = "$2b$12$" + "a" * 53


async def _company(
    session: AsyncSession, name: str = "Aide et Soins", accepting: bool = True
) -> Company:
    """Store a company and return it.

    Args:
        session (AsyncSession): The open session.
        name (str): The trading name.
        accepting (bool): Whether it accepts applications.

    Returns:
        Company: The stored company.
    """
    return await CompanyRepository(session).create(
        Company(name=name, is_accepting_applications=accepting)
    )


def _application(company_id: str, **overrides: ModelInput) -> HcaApplication:
    """Build an application.

    Args:
        company_id (str): The company applied to.
        **overrides (ModelInput): Fields to replace.

    Returns:
        HcaApplication: The application.
    """
    values: Dict[str, ModelInput] = {
        "company_id": company_id,
        "first_name": "Ana",
        "last_name": "Lopez",
        "phone_number": "+33611223344",
        "email": "ana.lopez@example.com",
        "address": {
            "street": "9 rue Oberkampf",
            "postal_code": "75011",
            "city": "Paris",
            "latitude": 48.8650,
            "longitude": 2.3780,
        },
        "hashed_password": HASH,
    }
    values.update(overrides)
    return HcaApplication(**values)


class TestCompanyRepository:
    """Tests for storing the agencies an applicant chooses between."""

    async def test_a_company_round_trips(self, session: AsyncSession) -> None:
        """Every field survives storage."""
        stored = await CompanyRepository(session).create(
            Company(
                name="Aide et Soins",
                registration_number="123456789",
                contact_email="hello@example.com",
                address={
                    "street": "1 rue de la Paix",
                    "postal_code": "75002",
                    "city": "Paris",
                    "latitude": 48.8690,
                    "longitude": 2.3310,
                },
            )
        )

        loaded = await CompanyRepository(session).get(stored.id)
        assert loaded is not None
        assert loaded.name == "Aide et Soins"
        assert loaded.registration_number == "123456789"
        assert loaded.address is not None
        assert loaded.address.latitude == pytest.approx(48.8690)

    async def test_a_company_without_an_address_round_trips(
        self, session: AsyncSession
    ) -> None:
        """The address is optional, and stays absent rather than becoming blank.

        Notes:
            Rebuilding an empty address instead would send it to Nominatim on
            every read.
        """
        stored = await _company(session)

        loaded = await CompanyRepository(session).get(stored.id)
        assert loaded is not None
        assert loaded.address is None

    async def test_two_companies_cannot_share_a_name(
        self, session: AsyncSession
    ) -> None:
        """An applicant choosing between two identical names chooses at random."""
        await _company(session, name="Aide et Soins")

        with pytest.raises(IntegrityError):
            await _company(session, name="Aide et Soins")

    async def test_listing_can_exclude_closed_companies(
        self, session: AsyncSession
    ) -> None:
        """The public list only offers agencies that can act on an application."""
        await _company(session, name="Open Agency", accepting=True)
        await _company(session, name="Closed Agency", accepting=False)

        accepting = await CompanyRepository(session).list(accepting_only=True)
        assert [company.name for company in accepting] == ["Open Agency"]

    async def test_listing_is_ordered_by_name(self, session: AsyncSession) -> None:
        """A list somebody chooses from is easier to read alphabetically."""
        await _company(session, name="Zeta Care")
        await _company(session, name="Alpha Care")

        companies = await CompanyRepository(session).list()
        assert [company.name for company in companies] == ["Alpha Care", "Zeta Care"]


class TestHcaApplicationRepository:
    """Tests for storing an assistant's application."""

    async def test_an_application_round_trips(self, session: AsyncSession) -> None:
        """Every field survives storage, credential included."""
        company = await _company(session)
        stored = await HcaApplicationRepository(session).create(
            _application(company.id)
        )

        loaded = await HcaApplicationRepository(session).get(stored.id)
        assert loaded is not None
        assert loaded.email == "ana.lopez@example.com"
        assert loaded.hashed_password == HASH
        assert loaded.status is HcaApplicationStatus.PENDING
        assert loaded.address.latitude == pytest.approx(48.8650)

    async def test_the_same_person_may_apply_to_two_companies(
        self, session: AsyncSession
    ) -> None:
        """Looking for work in two places at once is legitimate.

        Notes:
            The email is deliberately not unique on this table, unlike on
            ``users``. A unique index here would refuse the second application
            and refuse a re-application after a rejection.
        """
        first = await _company(session, name="First Agency")
        second = await _company(session, name="Second Agency")
        repository = HcaApplicationRepository(session)

        await repository.create(_application(first.id))
        await repository.create(_application(second.id))

        assert await repository.count() == 2

    async def test_a_pending_application_is_found_per_company(
        self, session: AsyncSession
    ) -> None:
        """The duplicate check is scoped to the agency applied to."""
        first = await _company(session, name="First Agency")
        second = await _company(session, name="Second Agency")
        repository = HcaApplicationRepository(session)
        await repository.create(_application(first.id))

        assert (
            await repository.pending_for_email("ana.lopez@example.com", first.id)
            is not None
        )
        assert (
            await repository.pending_for_email("ana.lopez@example.com", second.id)
            is None
        )

    async def test_a_decided_application_is_not_pending(
        self, session: AsyncSession
    ) -> None:
        """Somebody previously declined may apply again."""
        company = await _company(session)
        repository = HcaApplicationRepository(session)
        stored = await repository.create(_application(company.id))

        await repository.update(
            stored.model_copy(
                update={
                    "status": HcaApplicationStatus.REJECTED,
                    "decided_by": "user-1",
                    "decided_at": datetime.now(UTC),
                }
            )
        )

        assert (
            await repository.pending_for_email("ana.lopez@example.com", company.id)
            is None
        )

    async def test_the_queue_is_oldest_first(self, session: AsyncSession) -> None:
        """Whoever has waited longest is at the top.

        Notes:
            The opposite of every other listing here, and deliberately: this is
            a queue somebody works through, not a feed.
        """
        company = await _company(session)
        repository = HcaApplicationRepository(session)
        await repository.create(_application(company.id, first_name="First"))
        await repository.create(
            _application(company.id, first_name="Second", email="second@example.com")
        )

        queue = await repository.list(status=HcaApplicationStatus.PENDING)
        assert [item.first_name for item in queue] == ["First", "Second"]

    async def test_an_application_cannot_name_an_absent_company(
        self, session: AsyncSession
    ) -> None:
        """The foreign key refuses an application addressed to nobody."""
        with pytest.raises(IntegrityError):
            await HcaApplicationRepository(session).create(_application("ghost"))

    async def test_the_queue_is_filtered_by_company(
        self, session: AsyncSession
    ) -> None:
        """One agency never sees another's applicants."""
        first = await _company(session, name="First Agency")
        second = await _company(session, name="Second Agency")
        repository = HcaApplicationRepository(session)
        await repository.create(_application(first.id, first_name="Ours"))
        await repository.create(
            _application(second.id, first_name="Theirs", email="theirs@example.com")
        )

        ours = await repository.list(company_id=first.id)
        assert [item.first_name for item in ours] == ["Ours"]


class TestPlanningSettingsRepository:
    """Tests for the single row of manager-owned rules."""

    async def test_it_reads_as_absent_before_seeding(
        self, session: AsyncSession
    ) -> None:
        """A fresh install has no stored rules yet."""
        assert await PlanningSettingsRepository(session).get() is None

    async def test_seeding_then_reading_round_trips(
        self, session: AsyncSession
    ) -> None:
        """The seeded values come back unchanged."""
        repository = PlanningSettingsRepository(session)
        await repository.seed(
            PlanningSettings(max_intervention_radius_km=25.0, lunch_break_minutes=75)
        )

        loaded = await repository.get()
        assert loaded is not None
        assert loaded.max_intervention_radius_km == 25.0
        assert loaded.lunch_break_minutes == 75

    async def test_seeding_twice_keeps_the_first(self, session: AsyncSession) -> None:
        """A second caller finds the row rather than colliding on the key.

        Notes:
            Two requests arriving together would otherwise both insert the same
            primary key, and the loser would fail on a constraint instead of
            simply finding the settings already there.
        """
        repository = PlanningSettingsRepository(session)
        await repository.seed(PlanningSettings(max_intervention_radius_km=25.0))

        second = await repository.seed(
            PlanningSettings(max_intervention_radius_km=99.0)
        )

        assert second.max_intervention_radius_km == 25.0

    async def test_updating_records_who_changed_it(self, session: AsyncSession) -> None:
        """A radius that quietly halved is a question with a name attached."""
        repository = PlanningSettingsRepository(session)
        await repository.seed(PlanningSettings(max_intervention_radius_km=25.0))

        updated = await repository.update(
            PlanningSettings(
                max_intervention_radius_km=40.0,
                lunch_break_minutes=90,
                updated_by="user-1",
                updated_at=datetime.now(UTC),
            )
        )

        assert updated is not None
        assert updated.max_intervention_radius_km == 40.0
        assert updated.updated_by == "user-1"

    async def test_updating_before_seeding_reports_rather_than_creating(
        self, session: AsyncSession
    ) -> None:
        """An update arriving first is a caller that skipped a step.

        Notes:
            Quietly creating the row would hide the ordering mistake rather
            than surface it.
        """
        assert (
            await PlanningSettingsRepository(session).update(
                PlanningSettings(max_intervention_radius_km=40.0)
            )
            is None
        )

    async def test_the_working_day_survives_the_round_trip(
        self, session: AsyncSession
    ) -> None:
        """All four new columns are written and read back.

        Notes:
            A mapper that dropped one of them would leave the solver planning
            on a default the manager never chose — and the read would look
            successful, because the field would simply carry its default.
        """
        repository = PlanningSettingsRepository(session)
        await repository.seed(
            PlanningSettings(
                max_intervention_radius_km=25.0,
                day_start_minute=8 * 60,
                day_end_minute=19 * 60,
                lunch_break_minutes=75,
                lunch_window_start_minute=12 * 60,
                lunch_window_end_minute=14 * 60,
            )
        )

        loaded = await repository.get()
        assert loaded is not None
        assert loaded.day_start_minute == 8 * 60
        assert loaded.day_end_minute == 19 * 60
        assert loaded.lunch_break_minutes == 75
        assert loaded.lunch_window_start_minute == 12 * 60
        assert loaded.lunch_window_end_minute == 14 * 60

    async def test_updating_moves_the_working_day(self, session: AsyncSession) -> None:
        """A manager's new hours reach the row, not just the radius."""
        repository = PlanningSettingsRepository(session)
        await repository.seed(PlanningSettings(max_intervention_radius_km=25.0))

        updated = await repository.update(
            PlanningSettings(
                max_intervention_radius_km=25.0,
                day_start_minute=7 * 60,
                day_end_minute=21 * 60,
                lunch_window_start_minute=11 * 60,
                lunch_window_end_minute=15 * 60,
                updated_by="user-1",
                updated_at=datetime.now(UTC),
            )
        )

        assert updated is not None
        assert updated.day_start_minute == 7 * 60
        assert updated.day_end_minute == 21 * 60
        assert updated.lunch_window_start_minute == 11 * 60
        assert updated.lunch_window_end_minute == 15 * 60


class TestAccountColumns:
    """Tests for the three columns the two account paths added."""

    async def test_a_staff_created_account_round_trips(
        self, session: AsyncSession
    ) -> None:
        """The flag and the origin survive storage.

        Notes:
            If either were lost, an account created with a temporary password
            would come back looking like an ordinary one and the mandatory
            change would silently not apply.
        """
        stored = await UserRepository(session).create(
            User(
                email="new@example.com",
                full_name="New Starter",
                hashed_password=HASH,
                role=UserRole.MANAGER,
                company_id="company-1",
                account_origin=AccountOrigin.CREATED_BY_STAFF,
                must_change_password=True,
            )
        )

        loaded = await UserRepository(session).get(stored.id)
        assert loaded is not None
        assert loaded.must_change_password is True
        assert loaded.account_origin is AccountOrigin.CREATED_BY_STAFF
        assert loaded.company_id == "company-1"

    async def test_an_account_reads_back_after_changing_its_password(
        self, session: AsyncSession
    ) -> None:
        """The post-change state is representable and loadable.

        Notes:
            **This is the case an earlier version of the model made
            impossible.** The invariant keyed only on the origin and the flag,
            so a staff account that had done exactly what it was told could not
            be read back out of the database.
        """
        repository = UserRepository(session)
        stored = await repository.create(
            User(
                company_id="company-1",
                email="new@example.com",
                full_name="New Starter",
                hashed_password=HASH,
                role=UserRole.MANAGER,
                account_origin=AccountOrigin.CREATED_BY_STAFF,
                must_change_password=True,
            )
        )
        await repository.update(
            stored.model_copy(
                update={
                    "hashed_password": HASH,
                    "must_change_password": False,
                    "password_changed_at": datetime.now(UTC),
                }
            )
        )

        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.must_change_password is False
        assert loaded.password_changed_at is not None

    async def test_an_existing_account_defaults_to_self_registered(
        self, session: AsyncSession
    ) -> None:
        """Accounts made before the two paths existed are unaffected."""
        stored = await UserRepository(session).create(
            User(
                company_id="company-1",
                email="old@example.com",
                full_name="Old Hand",
                hashed_password=HASH,
                role=UserRole.MANAGER,
            )
        )

        loaded = await UserRepository(session).get(stored.id)
        assert loaded is not None
        assert loaded.account_origin is AccountOrigin.SELF_REGISTERED
        assert loaded.must_change_password is False
