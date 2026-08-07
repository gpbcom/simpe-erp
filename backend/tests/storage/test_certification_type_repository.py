from __future__ import annotations

# Third-party imports
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

# First-party imports
from models.catalog.certification_type import CertificationType
from storage.repositories.catalog.certification_type import CertificationTypeRepository


def _entry(code: str = "DEAES", is_active: bool = True) -> CertificationType:
    """Build a catalogue entry.

    Args:
        code (str): The code to assign.
        is_active (bool): Whether it may still be required.

    Returns:
        CertificationType: The entry.
    """
    return CertificationType(
        code=code,
        label=f"Diplome {code}",
        description=f"Le diplome {code}.",
        is_active=is_active,
    )


class TestCertificationTypeRepository:
    """Tests for reading and writing the certification catalogue."""

    async def test_an_entry_round_trips(self, session: AsyncSession) -> None:
        """Everything stored comes back unchanged."""
        repository = CertificationTypeRepository(session)

        stored = await repository.create(_entry())
        read = await repository.get(stored.id or "")

        assert read is not None
        assert read.code == "DEAES"
        assert read.label == "Diplome DEAES"
        assert read.description == "Le diplome DEAES."
        assert read.is_active is True

    async def test_the_code_is_unique(self, session: AsyncSession) -> None:
        """Two entries with one code break every match made against it."""
        repository = CertificationTypeRepository(session)
        await repository.create(_entry())

        with pytest.raises(IntegrityError):
            await repository.create(_entry())

    async def test_an_entry_is_found_by_code(self, session: AsyncSession) -> None:
        """A lookup takes a bare string off the wire and normalises it.

        Notes:
            The model upper-cases on the way in, but a query parameter has seen
            no model at all.
        """
        repository = CertificationTypeRepository(session)
        await repository.create(_entry())

        assert (await repository.get_by_code("  deaes  ")) is not None

    async def test_an_unknown_code_is_reported_as_absent(
        self, session: AsyncSession
    ) -> None:
        """A missing entry is ``None``, not an error."""
        assert await CertificationTypeRepository(session).get_by_code("GHOST") is None

    async def test_known_codes_answers_in_one_query(
        self, session: AsyncSession
    ) -> None:
        """The set every requirement is validated against.

        Notes:
            A set rather than a list, and one query rather than one per code: a
            catalogue entry saved with five codes would otherwise cost five
            round trips to say "all fine".
        """
        repository = CertificationTypeRepository(session)
        await repository.create(_entry("DEAES"))
        await repository.create(_entry("SST"))

        assert await repository.known_codes() == {"DEAES", "SST"}

    async def test_known_codes_hides_retired_entries(
        self, session: AsyncSession
    ) -> None:
        """Retiring is how a qualification stops being asked for.

        Notes:
            A new requirement naming a retired code is refused because it is
            absent from this set; including it would quietly undo the
            retirement.
        """
        repository = CertificationTypeRepository(session)
        await repository.create(_entry("DEAES", is_active=False))

        assert await repository.known_codes() == set()
        assert await repository.known_codes(include_inactive=True) == {"DEAES"}

    async def test_listing_is_ordered_by_label(self, session: AsyncSession) -> None:
        """Ordered by what a manager reads, not by the machine-safe key."""
        repository = CertificationTypeRepository(session)
        await repository.create(_entry("SST"))
        await repository.create(_entry("ADVF"))

        listed = await repository.list()

        assert [entry.code for entry in listed] == ["ADVF", "SST"]

    async def test_listing_hides_retired_entries_by_default(
        self, session: AsyncSession
    ) -> None:
        """A screen offering a requirement offers only what may be required."""
        repository = CertificationTypeRepository(session)
        await repository.create(_entry("DEAES"))
        await repository.create(_entry("SST", is_active=False))

        assert [entry.code for entry in await repository.list()] == ["DEAES"]
        assert len(await repository.list(include_inactive=True)) == 2

    async def test_an_entry_is_updated(self, session: AsyncSession) -> None:
        """A stored entry takes the new values."""
        repository = CertificationTypeRepository(session)
        stored = await repository.create(_entry())

        updated = await repository.update(
            stored.model_copy(update={"label": "Renamed", "is_active": False})
        )

        assert updated is not None
        assert updated.label == "Renamed"
        assert updated.is_active is False

    async def test_updating_an_absent_entry_reports_nothing_matched(
        self, session: AsyncSession
    ) -> None:
        """An update that matches nothing answers ``None`` rather than raising."""
        repository = CertificationTypeRepository(session)

        assert (
            await repository.update(_entry().model_copy(update={"id": "ghost"})) is None
        )

    async def test_an_entry_is_deleted(self, session: AsyncSession) -> None:
        """An entry added by mistake refers to nothing and can go."""
        repository = CertificationTypeRepository(session)
        stored = await repository.create(_entry())

        assert await repository.delete(stored.id or "") is True
        assert await repository.get(stored.id or "") is None

    async def test_deleting_an_absent_entry_answers_false(
        self, session: AsyncSession
    ) -> None:
        """ "Nothing matched" is a meaningful answer, not an error."""
        assert await CertificationTypeRepository(session).delete("ghost") is False

    async def test_counting_matches_the_listing(self, session: AsyncSession) -> None:
        """The count and the page agree about what is retired."""
        repository = CertificationTypeRepository(session)
        await repository.create(_entry("DEAES"))
        await repository.create(_entry("SST", is_active=False))

        assert await repository.count() == 1
        assert await repository.count(include_inactive=True) == 2
