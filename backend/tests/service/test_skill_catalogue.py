from __future__ import annotations

# Standard library imports
from typing import List
from unittest.mock import AsyncMock

# Third-party imports
from sqlalchemy.exc import IntegrityError
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.catalog.skill_type import SkillType
from models.enums import ContractType
from models.people.hca import Hca
from models.people.hca.skill import Skill
from service.skills.exceptions import (
    MTSkillTypeAlreadyExists,
    MTSkillTypeInUse,
    MTSkillTypeNotFound,
    MTSkillTypeUnknownCode,
)
from service.skills.skills import SkillTypeService


def _entry(code: str = "TOILETTE", is_active: bool = True) -> SkillType:
    """Build a catalogue entry.

    Args:
        code (str): The code to assign.
        is_active (bool): Whether it may still be required.

    Returns:
        SkillType: The entry.
    """
    return SkillType(
        id=f"type-{code.lower()}",
        code=code,
        label=f"Competence {code}",
        is_active=is_active,
    )


def _hca(codes: List[str]) -> Hca:
    """Build an assistant who has declared some skills.

    Args:
        codes (List[str]): The catalogue codes they declared.

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
        skills=[Skill(name=code, code=code) for code in codes],
    )


def _service(code: str = "TOILETTE") -> SkillTypeService:
    """Build a service over stand-in repositories holding one entry.

    Args:
        code (str): The code the catalogue offers.

    Returns:
        SkillTypeService: The service under test.
    """
    skills = AsyncMock()
    skills.get.return_value = _entry(code)
    skills.known_codes.return_value = {code}
    skills.create.side_effect = lambda entry: entry
    skills.update.side_effect = lambda entry: entry
    skills.delete.return_value = True
    hcas = AsyncMock()
    hcas.list_all.return_value = []
    types = AsyncMock()
    types.list.return_value = []
    return SkillTypeService(skills=skills, hcas=hcas, types=types)


class TestAssertKnown:
    """Tests for the referential integrity the JSON column cannot have."""

    async def test_no_requirement_needs_no_check(self) -> None:
        """The common case costs nothing, not even a query."""
        service = _service()

        await service.assert_known([])

        service.skills.known_codes.assert_not_awaited()

    async def test_a_known_code_passes(self) -> None:
        """A requirement the catalogue offers is stored."""
        await _service().assert_known(["TOILETTE"])

    async def test_the_check_is_case_insensitive(self) -> None:
        """A lower-cased code off the wire still matches the catalogue."""
        await _service().assert_known(["toilette"])

    async def test_an_unknown_code_is_refused_by_name(self) -> None:
        """The message names the typo and lists what is on offer.

        Notes:
            A foreign key cannot reach inside a JSON array, so this check is
            the integrity constraint — and it produces a better message than a
            constraint would.
        """
        with pytest.raises(MTSkillTypeUnknownCode) as raised:
            await _service().assert_known(["TOILETTE", "TOILLETE"])

        assert "TOILLETE" in str(raised.value)
        assert "TOILETTE" in str(raised.value)

    async def test_one_query_serves_every_code(self) -> None:
        """Five codes cost one round trip, not five."""
        service = _service()

        await service.assert_known(["TOILETTE", "TOILETTE", "toilette"])

        service.skills.known_codes.assert_awaited_once()

    async def test_a_retired_code_is_refused(self) -> None:
        """Retiring is how a skill stops being asked for.

        Notes:
            ``known_codes`` hides retired entries by default, so a new
            requirement naming one is refused — letting it through would
            quietly undo the retirement.
        """
        service = _service()
        service.skills.known_codes.return_value = set()

        with pytest.raises(MTSkillTypeUnknownCode):
            await service.assert_known(["TOILETTE"])

    async def test_an_empty_catalogue_says_so(self) -> None:
        """ "The catalogue offers: nothing yet" is the actionable message."""
        service = _service()
        service.skills.known_codes.return_value = set()

        with pytest.raises(MTSkillTypeUnknownCode) as raised:
            await service.assert_known(["TOILETTE"])

        assert "nothing yet" in str(raised.value)


class TestCatalogueWrites:
    """Tests for adding, changing and reading catalogue entries."""

    async def test_an_entry_is_created(self) -> None:
        """The ordinary case works."""
        assert (await _service().create(_entry())).code == "TOILETTE"

    async def test_a_duplicate_code_is_refused(self) -> None:
        """The unique index is translated into a 409 with a reason."""
        service = _service()
        service.skills.create.side_effect = IntegrityError("", {}, Exception())

        with pytest.raises(MTSkillTypeAlreadyExists):
            await service.create(_entry())

    async def test_an_absent_entry_is_reported(self) -> None:
        """A missing entry raises rather than returning ``None``."""
        service = _service()
        service.skills.get.return_value = None

        with pytest.raises(MTSkillTypeNotFound):
            await service.get("ghost")

    async def test_an_update_leaves_omitted_fields_alone(self) -> None:
        """A partial edit is partial.

        Notes:
            Without this the route's ``exclude_unset`` would be pointless: a
            label change would reset the description to ``None``.
        """
        service = _service()
        service.skills.get.return_value = _entry().model_copy(
            update={"description": "Kept."}
        )

        updated = await service.update("type-toilette", label="Renamed")

        assert updated.label == "Renamed"
        assert updated.description == "Kept."

    async def test_an_update_cannot_change_the_code(self) -> None:
        """``code`` is not a parameter, so no call can rename it.

        Notes:
            **This test is the rule.** Renaming a code would leave a workforce
            having declared skills for a code that no longer exists and
            un-skill all of them on the next planning run.
        """
        updated = await _service().update("type-toilette", label="Renamed")

        assert updated.code == "TOILETTE"

    async def test_an_update_to_a_vanished_entry_is_reported(self) -> None:
        """A row deleted between the read and the write is a 404, not a 500."""
        service = _service()
        service.skills.update.side_effect = None
        service.skills.update.return_value = None

        with pytest.raises(MTSkillTypeNotFound):
            await service.update("type-toilette", label="Renamed")


class TestCatalogueDeletion:
    """Tests for the check that stands in for a missing foreign key."""

    async def test_an_unreferenced_entry_is_removed(self) -> None:
        """An entry added by mistake this morning refers to nothing."""
        service = _service()

        await service.delete("type-toilette")

        service.skills.delete.assert_awaited_once_with("type-toilette")

    async def test_an_entry_somebody_declared_is_refused(self) -> None:
        """Deleting it would strand the declaration naming it."""
        service = _service()
        service.hcas.list_all.return_value = [_hca(["TOILETTE"])]

        with pytest.raises(MTSkillTypeInUse) as raised:
            await service.delete("type-toilette")

        assert "1 assistant(s)" in str(raised.value)
        service.skills.delete.assert_not_awaited()

    async def test_an_entry_a_service_requires_is_refused(self) -> None:
        """Deleting it would leave a requirement pointing at nothing.

        Notes:
            A requirement pointing at nothing fails every planning run it
            touches, with a diagnosis that reads as a staffing problem.
        """
        service = _service()
        service.types.list.return_value = [
            InterventionType(
                id="type-1",
                name="Soin",
                code="SOIN",
                service_category="necessity",
                required_skill_codes=["TOILETTE"],
            )
        ]

        with pytest.raises(MTSkillTypeInUse) as raised:
            await service.delete("type-toilette")

        assert "1 service(s)" in str(raised.value)

    async def test_the_refusal_offers_retirement(self) -> None:
        """ "Cannot delete" with no remedy is worked around, not obeyed."""
        service = _service()
        service.hcas.list_all.return_value = [_hca(["TOILETTE"])]

        with pytest.raises(MTSkillTypeInUse) as raised:
            await service.delete("type-toilette")

        assert "Retire it instead" in str(raised.value)

    async def test_an_unrelated_declaration_does_not_block(self) -> None:
        """Only the code being deleted counts."""
        service = _service()
        service.hcas.list_all.return_value = [_hca(["ARABE"])]

        await service.delete("type-toilette")

        service.skills.delete.assert_awaited_once()

    async def test_a_certification_of_the_same_code_does_not_block(self) -> None:
        """The two catalogues are separate all the way down.

        Notes:
            An assistant holding the *certification* ``TOILETTE`` is not
            somebody who declared the *skill* ``TOILETTE``, and counting them
            would refuse a delete that is perfectly safe.
        """
        service = _service()
        assistant = _hca([])
        service.hcas.list_all.return_value = [
            assistant.model_copy(
                update={
                    "certifications": [{"name": "TOILETTE", "code": "TOILETTE"}],
                    "skills": [],
                }
            )
        ]

        await service.delete("type-toilette")

        service.skills.delete.assert_awaited_once()
