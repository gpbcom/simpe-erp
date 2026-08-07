from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Any, Dict

# Third-party imports
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import AvailabilityKind, ContractType, Weekday
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.hca.certification import Certification
from models.people.hca import Hca
from storage.repositories.people.hca import HcaRepository


def _slot(
    hca_id: str,
    start: date,
    end: date,
    kind: AvailabilityKind = AvailabilityKind.HOLIDAY,
) -> AvailabilitySlot:
    """Build a whole-day absence for a period.

    Args:
        hca_id (str): The assistant the absence belongs to.
        start (date): First day of the period.
        end (date): Last day of the period.
        kind (AvailabilityKind): Why the assistant is unavailable.

    Returns:
        AvailabilitySlot: The absence.
    """
    return AvailabilitySlot(hca_id=hca_id, start_date=start, end_date=end, kind=kind)


class TestHcaRepository:
    """Tests for the HcaRepository."""

    # ------------------------------------------------------------------ #
    #  Create and read
    # ------------------------------------------------------------------ #

    async def test_create_assigns_an_identifier(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A stored assistant comes back with a generated identifier."""
        stored = await HcaRepository(session).create(hca)
        assert stored.id is not None

    async def test_round_trip_preserves_the_home_address(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The home address is the routing depot, so it must survive intact."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.address.street == "5 avenue de la Gare"
        assert loaded.address.latitude == pytest.approx(48.8443)

    async def test_timestamps_come_back_timezone_aware(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """Timestamps are UTC-aware regardless of the backend.

        Notes:
            SQLite has no timezone type and returns a naive value; the mapper
            normalises it so test and production agree.
        """
        stored = await HcaRepository(session).create(hca)
        assert stored.created_at is not None
        assert stored.created_at.tzinfo is not None

    async def test_get_returns_none_for_an_unknown_id(
        self, session: AsyncSession
    ) -> None:
        """An absent assistant reads as None."""
        assert await HcaRepository(session).get("no-such-id") is None

    # ------------------------------------------------------------------ #
    #  Driving licence round trip
    # ------------------------------------------------------------------ #

    async def test_an_assistant_without_a_licence_reads_back_as_none(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """Four NULL licence columns mean no licence, not an empty one."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.driving_license is None
        assert loaded.can_drive() is False

    async def test_a_licence_survives_the_round_trip(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Categories flattened into one column rebuild into a licence."""
        repository = HcaRepository(session)
        stored = await repository.create(
            Hca(
                company_id="company-1",
                **{
                    **hca_kwargs,
                    "driving_license": {
                        "categories": ["B", "A2"],
                        "number": "12AB34567",
                    },
                },
            )
        )
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.driving_license is not None
        assert loaded.driving_license.categories == ["B", "A2"]
        assert loaded.driving_license.number == "12AB34567"
        assert loaded.can_drive() is True

    async def test_removing_a_licence_clears_every_column(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """An assistant who loses their licence keeps no trace of it.

        Notes:
            Clearing all four columns matters: leaving the old number behind
            would make ``can_drive`` disagree with the record.
        """
        repository = HcaRepository(session)
        stored = await repository.create(
            Hca(
                company_id="company-1",
                **{
                    **hca_kwargs,
                    "driving_license": {"categories": ["B"], "number": "12AB"},
                },
            )
        )
        cleared = await repository.update(
            stored.model_copy(update={"driving_license": None})
        )
        assert cleared is not None
        assert cleared.driving_license is None
        reloaded = await repository.get(stored.id)
        assert reloaded is not None
        assert reloaded.driving_license is None

    # ------------------------------------------------------------------ #
    #  Certifications
    # ------------------------------------------------------------------ #

    async def test_certifications_survive_the_round_trip(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Qualifications are stored in their own table and read back."""
        repository = HcaRepository(session)
        stored = await repository.create(
            Hca(
                company_id="company-1",
                **{
                    **hca_kwargs,
                    "certifications": [
                        {"name": "DEAVS", "issuer": "État"},
                        {"name": "Premiers secours"},
                    ],
                },
            )
        )
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert {entry.name for entry in loaded.certifications} == {
            "DEAVS",
            "Premiers secours",
        }

    # ------------------------------------------------------------------ #
    #  set_employment — the manager's only mutation
    # ------------------------------------------------------------------ #

    async def test_set_employment_changes_contract_and_certifications(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A manager may change exactly these three fields."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        updated = await repository.set_employment(
            stored.id,
            ContractType.CDD,
            [Certification(name="DEAVS")],
            field_employee=True,
        )
        assert updated is not None
        assert updated.contract_type is ContractType.CDD
        assert [entry.name for entry in updated.certifications] == ["DEAVS"]

    async def test_set_employment_touches_nothing_else(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Contact details, address and licence are left alone.

        Notes:
            This is the enforcement of "a manager may modify only the
            contract type, the certifications and whether this person goes out
            on rounds". A general update would let a stale payload clobber the
            rest of the record.
        """
        repository = HcaRepository(session)
        stored = await repository.create(
            Hca(
                company_id="company-1",
                **{**hca_kwargs, "driving_license": {"categories": ["B"]}},
            )
        )
        await repository.set_employment(
            stored.id, ContractType.INTERIM, [], field_employee=True
        )
        reloaded = await repository.get(stored.id)
        assert reloaded is not None
        assert reloaded.email == "luc.martin@example.com"
        assert reloaded.address.street == "5 avenue de la Gare"
        assert reloaded.driving_license is not None
        assert reloaded.can_drive() is True

    async def test_set_employment_replaces_certifications_wholesale(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """What is sent is what the assistant now holds."""
        repository = HcaRepository(session)
        stored = await repository.create(
            Hca(
                company_id="company-1",
                **{**hca_kwargs, "certifications": [{"name": "Old"}]},
            )
        )
        updated = await repository.set_employment(
            stored.id, ContractType.CDI, [Certification(name="New")], field_employee=True
        )
        assert updated is not None
        assert [entry.name for entry in updated.certifications] == ["New"]

    async def test_set_employment_takes_somebody_off_the_rounds(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """**The write that never happened.**

        Notes:
            ``field_employee`` carried a default of ``True`` here while the
            service did not forward the value it was sent, so this write was
            unreachable: a manager switching somebody off got a 200 and a row
            that still said ``True``. The argument is required now, and this
            asserts the value actually lands.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        updated = await repository.set_employment(
            stored.id, ContractType.CDI, [], field_employee=False
        )

        assert updated is not None
        assert updated.field_employee is False
        reloaded = await repository.get(stored.id)
        assert reloaded is not None
        assert reloaded.field_employee is False

    async def test_set_employment_puts_somebody_back_on_the_rounds(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The flag travels in both directions."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.set_employment(
            stored.id, ContractType.CDI, [], field_employee=False
        )

        updated = await repository.set_employment(
            stored.id, ContractType.CDI, [], field_employee=True
        )

        assert updated is not None
        assert updated.field_employee is True

    async def test_an_unrelated_employment_edit_does_not_restore_the_rounds_flag(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The second half of the same bug, and the nastier half.

        Notes:
            Because the value was never forwarded, the repository's own default
            of ``True`` was applied on **every** save — so a manager changing
            only somebody's contract silently put them back on the rounds. It
            is worse than the first half: nobody involved was thinking about
            the flag, and the next planning run simply scheduled them.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.set_employment(
            stored.id, ContractType.CDI, [], field_employee=False
        )

        await repository.set_employment(
            stored.id, ContractType.INTERIM, [], field_employee=False
        )

        reloaded = await repository.get(stored.id)
        assert reloaded is not None
        assert reloaded.contract_type is ContractType.INTERIM
        assert reloaded.field_employee is False

    async def test_set_employment_of_an_unknown_assistant_returns_none(
        self, session: AsyncSession
    ) -> None:
        """Changing an absent assistant reports rather than raising."""
        repository = HcaRepository(session)
        assert (
            await repository.set_employment(
                "no-such-id", ContractType.CDI, [], field_employee=True
            )
            is None
        )

    # ------------------------------------------------------------------ #
    #  Availability
    # ------------------------------------------------------------------ #

    async def test_add_availability_returns_the_stored_slot(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A filed absence comes back with its generated identifier."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        slot = await repository.add_availability(
            stored.id, _slot(stored.id, date(2026, 8, 10), date(2026, 8, 14))
        )
        assert slot is not None
        assert slot.id is not None
        assert slot.hca_id == stored.id

    async def test_an_absence_cannot_be_filed_against_another_assistant(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """The owning assistant comes from the path, never from the payload.

        Notes:
            Otherwise an assistant could book a colleague off work by naming
            them in the request body.
        """
        repository = HcaRepository(session)
        luc = await repository.create(Hca(company_id="company-1", **hca_kwargs))
        claire = await repository.create(
            Hca(
                company_id="company-1",
                **{
                    **hca_kwargs,
                    "last_name": "Bernard",
                    "email": "claire.bernard@example.com",
                },
            )
        )
        forged = _slot(claire.id, date(2026, 8, 10), date(2026, 8, 14))
        stored_slot = await repository.add_availability(luc.id, forged)
        assert stored_slot is not None
        assert stored_slot.hca_id == luc.id
        assert await repository.list_availability(claire.id) == []

    async def test_availability_is_loaded_with_the_assistant(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """An absence shows up on the assistant it belongs to."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.add_availability(
            stored.id, _slot(stored.id, date(2026, 8, 10), date(2026, 8, 14))
        )
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.is_available_on(date(2026, 8, 12)) is False
        assert loaded.is_available_on(date(2026, 8, 20)) is True

    async def test_a_partial_day_absence_round_trips(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A time window survives storage and stays a partial-day block."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.add_availability(
            stored.id,
            AvailabilitySlot(
                hca_id=stored.id,
                start_date=date(2026, 8, 12),
                end_date=date(2026, 8, 12),
                kind=AvailabilityKind.TRAINING,
                start_time=time(9, 0),
                end_time=time(12, 0),
            ),
        )
        loaded = await repository.get(stored.id)
        assert loaded is not None
        assert loaded.is_available_on(date(2026, 8, 12)) is True
        blocking = loaded.blocking_slots_on(date(2026, 8, 12))
        assert len(blocking) == 1
        assert blocking[0].start_time == time(9, 0)

    async def test_list_availability_finds_an_overlapping_absence(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """An absence starting before the window but running into it counts.

        Notes:
            Comparing only the start date would miss this case — precisely the
            one that breaks a planning.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.add_availability(
            stored.id, _slot(stored.id, date(2026, 8, 1), date(2026, 8, 12))
        )
        overlapping = await repository.list_availability(
            stored.id, start=date(2026, 8, 10), end=date(2026, 8, 16)
        )
        assert len(overlapping) == 1

    async def test_list_availability_excludes_a_disjoint_absence(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """An absence entirely outside the window is not returned."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.add_availability(
            stored.id, _slot(stored.id, date(2026, 7, 1), date(2026, 7, 5))
        )
        assert (
            await repository.list_availability(
                stored.id, start=date(2026, 8, 10), end=date(2026, 8, 16)
            )
            == []
        )

    async def test_remove_availability_withdraws_the_absence(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A withdrawn absence no longer blocks the day."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        slot = await repository.add_availability(
            stored.id, _slot(stored.id, date(2026, 8, 10), date(2026, 8, 14))
        )
        assert slot is not None
        assert await repository.remove_availability(stored.id, slot.id) is True
        assert await repository.list_availability(stored.id) == []

    async def test_an_absence_cannot_be_removed_by_another_assistant(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Knowing a slot id is not enough to delete a colleague's absence."""
        repository = HcaRepository(session)
        luc = await repository.create(Hca(company_id="company-1", **hca_kwargs))
        claire = await repository.create(
            Hca(
                company_id="company-1",
                **{
                    **hca_kwargs,
                    "last_name": "Bernard",
                    "email": "claire.bernard@example.com",
                },
            )
        )
        slot = await repository.add_availability(
            luc.id, _slot(luc.id, date(2026, 8, 10), date(2026, 8, 14))
        )
        assert slot is not None
        assert await repository.remove_availability(claire.id, slot.id) is False
        assert len(await repository.list_availability(luc.id)) == 1

    # ------------------------------------------------------------------ #
    #  Listing
    # ------------------------------------------------------------------ #

    async def test_list_all_returns_the_whole_workforce(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """The planning run needs everyone at once, unpaginated."""
        repository = HcaRepository(session)
        for index in range(3):
            await repository.create(
                Hca(
                    company_id="company-1",
                    **{
                        **hca_kwargs,
                        "last_name": f"Name{index}",
                        "email": f"hca{index}@example.com",
                    },
                )
            )
        assert len(await repository.list_all()) == 3

    async def test_list_all_on_an_empty_workforce(self, session: AsyncSession) -> None:
        """No assistants is an empty list, not an error."""
        assert await HcaRepository(session).list_all() == []

    async def test_the_contract_filter_restricts_the_page(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Filtering by contract returns only that contract."""
        repository = HcaRepository(session)
        await repository.create(Hca(company_id="company-1", **hca_kwargs))
        await repository.create(
            Hca(
                company_id="company-1",
                **{
                    **hca_kwargs,
                    "last_name": "Bernard",
                    "email": "claire.bernard@example.com",
                    "contract_type": ContractType.CDD,
                },
            )
        )
        listed = await repository.list(contract_type=ContractType.CDD)
        assert len(listed) == 1
        assert listed[0].last_name == "Bernard"

    async def test_count_matches_the_list_filters(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """A page total is computed from the filters that built the page."""
        repository = HcaRepository(session)
        await repository.create(Hca(company_id="company-1", **hca_kwargs))
        assert await repository.count() == 1
        assert await repository.count(contract_type=ContractType.CDD) == 0

    # ------------------------------------------------------------------ #
    #  Delete
    # ------------------------------------------------------------------ #

    async def test_delete_removes_the_assistant_and_its_children(
        self, session: AsyncSession, hca_kwargs: Dict[str, Any]
    ) -> None:
        """Certifications and absences go with the assistant.

        Notes:
            An orphaned absence would silently block scheduling for somebody
            who no longer exists.
        """
        repository = HcaRepository(session)
        stored = await repository.create(
            Hca(
                company_id="company-1",
                **{**hca_kwargs, "certifications": [{"name": "DEAVS"}]},
            )
        )
        await repository.add_availability(
            stored.id, _slot(stored.id, date(2026, 8, 10), date(2026, 8, 14))
        )
        assert await repository.delete(stored.id) is True
        assert await repository.get(stored.id) is None
        assert await repository.list_availability(stored.id) == []

    async def test_delete_of_an_unknown_assistant_reports_false(
        self, session: AsyncSession
    ) -> None:
        """Deleting an absent assistant is a no-op."""
        assert await HcaRepository(session).delete("no-such-id") is False

    # ------------------------------------------------------------------ #
    #  Working week
    # ------------------------------------------------------------------ #

    async def test_a_new_assistant_stores_the_standard_week(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The model's default reaches the column on insert.

        Args:
            session (AsyncSession): The database session.
            hca (Hca): The assistant fixture.
        """
        stored = await HcaRepository(session).create(hca)

        assert stored.working_weekdays == [
            Weekday.MONDAY,
            Weekday.TUESDAY,
            Weekday.WEDNESDAY,
            Weekday.THURSDAY,
            Weekday.FRIDAY,
        ]

    async def test_a_working_week_survives_the_round_trip(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The delimited column rebuilds the same list it was written from.

        Args:
            session (AsyncSession): The database session.
            hca (Hca): The assistant fixture.
        """
        repository = HcaRepository(session)
        stored = await repository.create(
            hca.model_copy(
                update={"working_weekdays": [Weekday.TUESDAY, Weekday.SATURDAY]}
            )
        )

        loaded = await repository.get(stored.id or "")
        assert loaded is not None
        assert loaded.working_weekdays == [Weekday.TUESDAY, Weekday.SATURDAY]

    async def test_set_working_weekdays_replaces_the_week(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The whole week is replaced, not merged with the stored one.

        Args:
            session (AsyncSession): The database session.
            hca (Hca): The assistant fixture.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        updated = await repository.set_working_weekdays(
            stored.id or "", [Weekday.SATURDAY, Weekday.SUNDAY]
        )

        assert updated is not None
        assert updated.working_weekdays == [Weekday.SATURDAY, Weekday.SUNDAY]

    async def test_set_working_weekdays_touches_nothing_else(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A narrow mutation stays narrow.

        Args:
            session (AsyncSession): The database session.
            hca (Hca): The assistant fixture.

        Notes:
            The working week is the assistant's own to set. If this method also
            rewrote the address, an assistant editing their rota could move
            their own routing depot.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        updated = await repository.set_working_weekdays(
            stored.id or "", [Weekday.MONDAY]
        )

        assert updated is not None
        assert updated.email == stored.email
        assert updated.address.street == stored.address.street
        assert updated.contract_type is stored.contract_type
        assert updated.field_employee is stored.field_employee

    async def test_set_working_weekdays_is_order_insensitive(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """Two spellings of one week produce one stored value.

        Args:
            session (AsyncSession): The database session.
            hca (Hca): The assistant fixture.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        shuffled = await repository.set_working_weekdays(
            stored.id or "", [Weekday.FRIDAY, Weekday.MONDAY]
        )
        ordered = await repository.set_working_weekdays(
            stored.id or "", [Weekday.MONDAY, Weekday.FRIDAY]
        )

        assert shuffled is not None and ordered is not None
        assert shuffled.working_weekdays == ordered.working_weekdays

    async def test_set_working_weekdays_of_an_unknown_assistant_returns_none(
        self, session: AsyncSession
    ) -> None:
        """A week set on nobody reports rather than inventing a record.

        Args:
            session (AsyncSession): The database session.
        """
        assert (
            await HcaRepository(session).set_working_weekdays(
                "ghost", [Weekday.MONDAY]
            )
            is None
        )
