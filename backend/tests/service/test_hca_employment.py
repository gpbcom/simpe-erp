from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.enums import ContractType
from models.people.hca.certification import Certification
from models.people.hca import Hca
from service.hcas.exceptions import MTHcaNotFound
from service.hcas.hcas import HcaService


def _hca(field_employee: bool = True) -> Hca:
    """Build a geocoded assistant.

    Args:
        field_employee (bool): Whether they may be placed on a planning.

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
        field_employee=field_employee,
    )


def _service() -> HcaService:
    """Build a service over a stand-in assistant store.

    Returns:
        HcaService: The service under test.
    """
    hcas = AsyncMock()
    hcas.set_employment.return_value = _hca()
    return HcaService(hcas=hcas)


class TestSetEmployment:
    """Tests for the only mutation a manager may make to an assistant."""

    async def test_all_three_fields_reach_the_store(self) -> None:
        """**The argument that used to be dropped.**

        Notes:
            The service took three parameters while the request model carried
            four, so ``field_employee`` was discarded here and the repository's
            own default put it back to ``True``. Asserting the whole call is
            what makes a dropped argument a failure rather than a wrong row.
        """
        service = _service()

        await service.set_employment(
            "hca-1", ContractType.CDD, [Certification(name="DEAVS")], False
        )

        arguments = service.hcas.set_employment.await_args.args
        assert len(arguments) == 4
        hca_id, contract_type, certifications, field_employee = arguments
        assert hca_id == "hca-1"
        assert contract_type is ContractType.CDD
        assert [entry.name for entry in certifications] == ["DEAVS"]
        assert field_employee is False

    @pytest.mark.parametrize("flag", [True, False])
    async def test_the_flag_travels_in_both_directions(self, flag: bool) -> None:
        """Off and on are both real edits a manager makes."""
        service = _service()

        await service.set_employment("hca-1", ContractType.CDI, [], flag)

        assert service.hcas.set_employment.await_args.args[3] is flag

    async def test_taking_somebody_off_the_rounds_is_logged_as_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A withdrawal is the change worth finding in a log afterwards.

        Notes:
            The planning run that then fails to place a visit is far easier to
            explain with this line than without it — the record itself only
            shows the state, never when it changed or on whose request.
        """
        service = _service()

        with caplog.at_level("WARNING"):
            await service.set_employment("hca-1", ContractType.CDI, [], False)

        assert any(
            "not a field employee" in record.message for record in caplog.records
        )

    async def test_putting_somebody_on_the_rounds_is_not_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Only the withdrawal is worth raising a voice about."""
        service = _service()

        with caplog.at_level("WARNING"):
            await service.set_employment("hca-1", ContractType.CDI, [], True)

        assert not [
            record for record in caplog.records if record.levelname == "WARNING"
        ]

    async def test_an_absent_assistant_is_reported(self) -> None:
        """A vanished record raises rather than returning ``None``."""
        service = _service()
        service.hcas.set_employment.return_value = None

        with pytest.raises(MTHcaNotFound):
            await service.set_employment("ghost", ContractType.CDI, [], True)
