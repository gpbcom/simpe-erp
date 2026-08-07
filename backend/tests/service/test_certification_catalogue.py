from __future__ import annotations

# Standard library imports
from typing import List
from unittest.mock import AsyncMock

# Third-party imports
from sqlalchemy.exc import IntegrityError
import pytest

# First-party imports
from models.catalog.certification_type import CertificationType
from models.catalog.intervention_type import InterventionType
from models.enums import ContractType
from models.people.hca.certification import Certification
from models.people.hca import Hca
from service.certifications.certifications import CertificationTypeService
from service.certifications.exceptions import (
    MTCertificationTypeAlreadyExists,
    MTCertificationTypeInUse,
    MTCertificationTypeNotFound,
    MTCertificationTypeUnknownCode,
)


def _entry(code: str = "DEAES", is_active: bool = True) -> CertificationType:
    """Build a catalogue entry.

    Args:
        code (str): The code to assign.
        is_active (bool): Whether it may still be required.

    Returns:
        CertificationType: The entry.
    """
    return CertificationType(
        id=f"type-{code.lower()}",
        code=code,
        label=f"Diplome {code}",
        is_active=is_active,
    )


def _hca(codes: List[str]) -> Hca:
    """Build an assistant holding some qualifications.

    Args:
        codes (List[str]): The catalogue codes they hold.

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
        certifications=[Certification(name=code, code=code) for code in codes],
    )


def _service(code: str = "DEAES") -> CertificationTypeService:
    """Build a service over stand-in repositories holding one entry.

    Args:
        code (str): The code the catalogue offers.

    Returns:
        CertificationTypeService: The service under test.
    """
    certifications = AsyncMock()
    certifications.get.return_value = _entry(code)
    certifications.known_codes.return_value = {code}
    certifications.create.side_effect = lambda entry: entry
    certifications.update.side_effect = lambda entry: entry
    certifications.delete.return_value = True
    hcas = AsyncMock()
    hcas.list_all.return_value = []
    types = AsyncMock()
    types.list.return_value = []
    return CertificationTypeService(
        certifications=certifications, hcas=hcas, types=types
    )


class TestAssertKnown:
    """Tests for the referential integrity the JSON column cannot have."""

    async def test_no_requirement_needs_no_check(self) -> None:
        """The common case costs nothing, not even a query."""
        service = _service()

        await service.assert_known([])

        service.certifications.known_codes.assert_not_awaited()

    async def test_a_known_code_passes(self) -> None:
        """A requirement the catalogue offers is stored."""
        await _service().assert_known(["DEAES"])

    async def test_the_check_is_case_insensitive(self) -> None:
        """A lower-cased code off the wire still matches the catalogue."""
        await _service().assert_known(["deaes"])

    async def test_an_unknown_code_is_refused_by_name(self) -> None:
        """The message names the typo and lists what is on offer.

        Notes:
            A foreign key cannot reach inside a JSON array, so this check is
            the integrity constraint — and it produces a better message than a
            constraint would, which is what somebody who has just mistyped a
            code needs.
        """
        with pytest.raises(MTCertificationTypeUnknownCode) as raised:
            await _service().assert_known(["DEAES", "DAESE"])

        assert "DAESE" in str(raised.value)
        assert "DEAES" in str(raised.value)

    async def test_one_query_serves_every_code(self) -> None:
        """Five codes cost one round trip, not five."""
        service = _service()

        await service.assert_known(["DEAES", "DEAES", "deaes"])

        service.certifications.known_codes.assert_awaited_once()

    async def test_a_retired_code_is_refused(self) -> None:
        """Retiring is how a qualification stops being asked for.

        Notes:
            ``known_codes`` hides retired entries by default, so a new
            requirement naming one is refused — letting it through would
            quietly undo the retirement.
        """
        service = _service()
        service.certifications.known_codes.return_value = set()

        with pytest.raises(MTCertificationTypeUnknownCode):
            await service.assert_known(["DEAES"])


class TestCatalogueWrites:
    """Tests for adding, changing and reading catalogue entries."""

    async def test_an_entry_is_created(self) -> None:
        """The ordinary case works."""
        assert (await _service().create(_entry())).code == "DEAES"

    async def test_a_duplicate_code_is_refused(self) -> None:
        """The unique index is translated into a 409 with a reason."""
        service = _service()
        service.certifications.create.side_effect = IntegrityError("", {}, Exception())

        with pytest.raises(MTCertificationTypeAlreadyExists):
            await service.create(_entry())

    async def test_an_absent_entry_is_reported(self) -> None:
        """A missing entry raises rather than returning ``None``."""
        service = _service()
        service.certifications.get.return_value = None

        with pytest.raises(MTCertificationTypeNotFound):
            await service.get("ghost")

    async def test_an_update_leaves_omitted_fields_alone(self) -> None:
        """A partial edit is partial.

        Notes:
            Without this the route's ``exclude_unset`` would be pointless: a
            label change would reset the description to ``None``.
        """
        service = _service()
        service.certifications.get.return_value = _entry().model_copy(
            update={"description": "Kept."}
        )

        updated = await service.update("type-deaes", label="Renamed")

        assert updated.label == "Renamed"
        assert updated.description == "Kept."

    async def test_an_update_cannot_change_the_code(self) -> None:
        """``code`` is not a parameter, so no call can rename it.

        Notes:
            **This test is the rule.** Renaming a code would leave a workforce
            holding certifications for a code that no longer exists and
            disqualify all of them on the next planning run.
        """
        updated = await _service().update("type-deaes", label="Renamed")

        assert updated.code == "DEAES"


class TestCatalogueDeletion:
    """Tests for the check that stands in for a missing foreign key."""

    async def test_an_unreferenced_entry_is_removed(self) -> None:
        """An entry added by mistake this morning refers to nothing."""
        service = _service()

        await service.delete("type-deaes")

        service.certifications.delete.assert_awaited_once_with("type-deaes")

    async def test_an_entry_somebody_holds_is_refused(self) -> None:
        """Deleting it would strand the qualification naming it."""
        service = _service()
        service.hcas.list_all.return_value = [_hca(["DEAES"])]

        with pytest.raises(MTCertificationTypeInUse) as raised:
            await service.delete("type-deaes")

        assert "1 assistant(s)" in str(raised.value)
        service.certifications.delete.assert_not_awaited()

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
                required_certification_codes=["DEAES"],
            )
        ]

        with pytest.raises(MTCertificationTypeInUse) as raised:
            await service.delete("type-deaes")

        assert "1 service(s)" in str(raised.value)

    async def test_the_refusal_offers_retirement(self) -> None:
        """ "Cannot delete" with no remedy is worked around, not obeyed."""
        service = _service()
        service.hcas.list_all.return_value = [_hca(["DEAES"])]

        with pytest.raises(MTCertificationTypeInUse) as raised:
            await service.delete("type-deaes")

        assert "Retire it instead" in str(raised.value)

    async def test_an_unrelated_qualification_does_not_block(self) -> None:
        """Only the code being deleted counts."""
        service = _service()
        service.hcas.list_all.return_value = [_hca(["SST"])]

        await service.delete("type-deaes")

        service.certifications.delete.assert_awaited_once()
