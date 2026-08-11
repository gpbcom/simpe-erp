from __future__ import annotations

# Third-party imports
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

# First-party imports
from models.catalog.skill_type import SkillType
from storage.repositories.catalog.skill_type import SkillTypeRepository


def _entry(code: str = "TOILETTE", is_active: bool = True) -> SkillType:
    """Build a catalogue entry.

    Args:
        code (str): The code to assign.
        is_active (bool): Whether it may still be required.

    Returns:
        SkillType: The entry.
    """
    return SkillType(
        code=code,
        label=f"Competence {code}",
        description=f"La competence {code}.",
        is_active=is_active,
    )


class TestSkillTypeRepository:
    """Tests for reading and writing the skill catalogue."""

    async def test_an_entry_round_trips(self, session: AsyncSession) -> None:
        """Everything stored comes back unchanged."""
        repository = SkillTypeRepository(session)

        stored = await repository.create(_entry())
        read = await repository.get(stored.id or "")

        assert read is not None
        assert read.code == "TOILETTE"
        assert read.label == "Competence TOILETTE"
        assert read.description == "La competence TOILETTE."
        assert read.is_active is True

    async def test_the_code_is_unique(self, session: AsyncSession) -> None:
        """Two entries with one code break every match made against it."""
        repository = SkillTypeRepository(session)
        await repository.create(_entry())

        with pytest.raises(IntegrityError):
            await repository.create(_entry())

    async def test_an_entry_is_found_by_code(self, session: AsyncSession) -> None:
        """A lookup takes a bare string off the wire and normalises it.

        Notes:
            The model upper-cases on the way in, but a query parameter has seen
            no model at all.
        """
        repository = SkillTypeRepository(session)
        await repository.create(_entry())

        assert (await repository.get_by_code("  toilette  ")) is not None

    async def test_an_unknown_code_is_reported_as_absent(
        self, session: AsyncSession
    ) -> None:
        """A missing entry is ``None``, not an error."""
        assert (await SkillTypeRepository(session).get_by_code("NOPE")) is None

    async def test_an_absent_entry_is_reported_as_none(
        self, session: AsyncSession
    ) -> None:
        """A missing identifier is ``None``, not an error."""
        assert (await SkillTypeRepository(session).get("nope")) is None

    async def test_known_codes_is_one_query_for_every_code(
        self, session: AsyncSession
    ) -> None:
        """The services validate a whole requirement against this in one go."""
        repository = SkillTypeRepository(session)
        await repository.create(_entry("TOILETTE"))
        await repository.create(_entry("ARABE"))

        assert await repository.known_codes() == {"TOILETTE", "ARABE"}

    async def test_known_codes_hides_retired_entries_by_default(
        self, session: AsyncSession
    ) -> None:
        """Retiring a skill is how it stops being asked for.

        Notes:
            Letting a new requirement name a retired code would quietly undo
            the retirement.
        """
        repository = SkillTypeRepository(session)
        await repository.create(_entry("TOILETTE"))
        await repository.create(_entry("ARABE", is_active=False))

        assert await repository.known_codes() == {"TOILETTE"}
        assert await repository.known_codes(include_inactive=True) == {
            "TOILETTE",
            "ARABE",
        }

    async def test_known_codes_is_empty_on_an_empty_catalogue(
        self, session: AsyncSession
    ) -> None:
        """An empty catalogue refuses every requirement, and says so."""
        assert await SkillTypeRepository(session).known_codes() == set()

    async def test_the_list_is_ordered_by_label(self, session: AsyncSession) -> None:
        """Ordered by what an assistant reads, not by the machine key."""
        repository = SkillTypeRepository(session)
        await repository.create(SkillType(code="B", label="Alpha"))
        await repository.create(SkillType(code="A", label="Beta"))

        assert [entry.label for entry in await repository.list()] == ["Alpha", "Beta"]

    async def test_the_list_hides_retired_entries_by_default(
        self, session: AsyncSession
    ) -> None:
        """The picker offers only what may still be declared."""
        repository = SkillTypeRepository(session)
        await repository.create(_entry("TOILETTE"))
        await repository.create(_entry("ARABE", is_active=False))

        assert len(await repository.list()) == 1
        assert len(await repository.list(include_inactive=True)) == 2

    async def test_the_count_matches_the_list(self, session: AsyncSession) -> None:
        """The two share one filter, so they cannot disagree."""
        repository = SkillTypeRepository(session)
        await repository.create(_entry("TOILETTE"))
        await repository.create(_entry("ARABE", is_active=False))

        assert await repository.count() == 1
        assert await repository.count(include_inactive=True) == 2

    async def test_an_update_is_stored(self, session: AsyncSession) -> None:
        """An entry is created once and edited for years."""
        repository = SkillTypeRepository(session)
        stored = await repository.create(_entry())

        updated = await repository.update(
            stored.model_copy(update={"label": "Toilette et habillage"})
        )

        assert updated is not None
        assert updated.label == "Toilette et habillage"

    async def test_an_update_without_an_id_is_refused(
        self, session: AsyncSession
    ) -> None:
        """There is no row to address."""
        assert (await SkillTypeRepository(session).update(_entry())) is None

    async def test_an_update_to_an_absent_entry_is_reported(
        self, session: AsyncSession
    ) -> None:
        """A vanished entry is ``None``, which the service turns into a 404."""
        repository = SkillTypeRepository(session)
        assert (
            await repository.update(_entry().model_copy(update={"id": "nope"}))
        ) is None

    async def test_an_entry_can_be_deleted(self, session: AsyncSession) -> None:
        """An entry added by mistake this morning refers to nothing."""
        repository = SkillTypeRepository(session)
        stored = await repository.create(_entry())

        assert await repository.delete(stored.id or "") is True
        assert (await repository.get(stored.id or "")) is None

    async def test_deleting_an_absent_entry_is_reported(
        self, session: AsyncSession
    ) -> None:
        """A delete that matched nothing answers ``False``, not an error."""
        assert await SkillTypeRepository(session).delete("nope") is False
