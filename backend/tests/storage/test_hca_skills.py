from __future__ import annotations

# Standard library imports
from datetime import date

# Third-party imports
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import ContractType
from models.people.hca.certification import Certification
from models.people.hca import Hca
from models.people.hca.skill import Skill
from storage.repositories.people.hca import HcaRepository


class TestHcaSkills:
    """Tests for declaring and withdrawing an assistant's own skills."""

    # ------------------------------------------------------------------ #
    #  Declaring
    # ------------------------------------------------------------------ #

    async def test_a_declared_skill_round_trips(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """Everything stored comes back on the assistant."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        await repository.add_skill(
            stored.id or "",
            Skill(
                name="Leve-personne",
                code="LEVE-PERSONNE",
                issuer="Formation interne",
                obtained_on=date(2024, 3, 1),
                expires_on=date(2027, 3, 1),
            ),
        )
        read = await repository.get(stored.id or "")

        assert read is not None
        assert len(read.skills) == 1
        declared = read.skills[0]
        assert declared.name == "Leve-personne"
        assert declared.code == "LEVE-PERSONNE"
        assert declared.issuer == "Formation interne"
        assert declared.obtained_on == date(2024, 3, 1)
        assert declared.expires_on == date(2027, 3, 1)

    async def test_a_declared_skill_is_given_an_identifier(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The store mints it, so no caller can point one at somebody else's row."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        declared = await repository.add_skill(stored.id or "", Skill(name="Portugais"))

        assert declared is not None
        assert declared.id is not None

    async def test_declaring_appends_rather_than_replaces(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The opposite of ``set_employment``, and deliberately so.

        Notes:
            A manager sends the whole certification list because they are
            editing a form. An assistant declares one skill at a time. A
            replace here would let somebody's second declaration silently
            delete their first.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        await repository.add_skill(stored.id or "", Skill(name="A", code="A"))
        await repository.add_skill(stored.id or "", Skill(name="B", code="B"))
        read = await repository.get(stored.id or "")

        assert read is not None
        assert {declared.code for declared in read.skills} == {"A", "B"}

    async def test_declaring_for_an_absent_assistant_is_reported(
        self, session: AsyncSession
    ) -> None:
        """A vanished assistant is ``None``, which the service turns into a 404."""
        assert (
            await HcaRepository(session).add_skill("nope", Skill(name="Portugais"))
        ) is None

    # ------------------------------------------------------------------ #
    #  Withdrawing
    # ------------------------------------------------------------------ #

    async def test_a_skill_can_be_withdrawn(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """Its owner, a manager or an administrator may remove it."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        declared = await repository.add_skill(stored.id or "", Skill(name="Portugais"))

        assert declared is not None
        assert await repository.remove_skill(stored.id or "", declared.id or "") is True

        read = await repository.get(stored.id or "")
        assert read is not None
        assert read.skills == []

    async def test_withdrawing_needs_the_owning_assistant(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """Knowing a skill id is not enough to strip a colleague of one.

        Notes:
            The assistant identifier is part of the lookup. Without it this
            would quietly take somebody off every visit that requires the
            skill, addressed only by a value the browser already holds.
        """
        repository = HcaRepository(session)
        owner = await repository.create(hca)
        colleague = await repository.create(
            Hca(
                first_name="Sophie",
                last_name="Bernard",
                phone_number="+33600000002",
                email="sophie.bernard@simple-erp.fr",
                address=hca.address,
                company_id=hca.company_id,
                contract_type=ContractType.CDI,
            )
        )
        declared = await repository.add_skill(owner.id or "", Skill(name="Portugais"))
        assert declared is not None

        assert (
            await repository.remove_skill(colleague.id or "", declared.id or "")
        ) is False

        read = await repository.get(owner.id or "")
        assert read is not None
        assert len(read.skills) == 1

    async def test_withdrawing_an_absent_skill_is_reported(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A delete that matched nothing answers ``False``, not an error."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)

        assert await repository.remove_skill(stored.id or "", "nope") is False

    # ------------------------------------------------------------------ #
    #  Interaction with the certification path
    # ------------------------------------------------------------------ #

    async def test_an_employment_change_leaves_the_skills_alone(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """The reason skills are a separate table, tested rather than asserted.

        Notes:
            ``set_employment`` replaces the certification list wholesale. Had
            the two shared a table, a manager saving a contract change would
            silently delete every skill the assistant had declared.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.add_skill(stored.id or "", Skill(name="Portugais", code="PT"))

        await repository.set_employment(
            stored.id or "",
            ContractType.CDD,
            [Certification(name="DEAES", code="DEAES")],
            field_employee=True,
        )
        read = await repository.get(stored.id or "")

        assert read is not None
        assert read.contract_type is ContractType.CDD
        assert [held.code for held in read.certifications] == ["DEAES"]
        assert [declared.code for declared in read.skills] == ["PT"]

    async def test_a_profile_update_keeps_the_skill_identifiers(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A client holds these identifiers so it can delete one.

        Notes:
            A write that renumbered them would turn a perfectly ordinary edit —
            changing a telephone number — into a silent invalidation of every
            delete link on the screen. That is why ``_skill_rows`` preserves an
            identifier where ``_certification_rows`` mints a fresh one.
        """
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        declared = await repository.add_skill(stored.id or "", Skill(name="Portugais"))
        assert declared is not None

        loaded = await repository.get(stored.id or "")
        assert loaded is not None
        await repository.update(
            loaded.model_copy(update={"phone_number": "+33600000009"})
        )

        read = await repository.get(stored.id or "")
        assert read is not None
        assert [entry.id for entry in read.skills] == [declared.id]

    async def test_skills_are_deleted_with_their_assistant(
        self, session: AsyncSession, hca: Hca
    ) -> None:
        """A skill has no meaning without the person who declared it."""
        repository = HcaRepository(session)
        stored = await repository.create(hca)
        await repository.add_skill(stored.id or "", Skill(name="Portugais"))

        assert await repository.delete(stored.id or "") is True
        assert (await repository.get(stored.id or "")) is None
