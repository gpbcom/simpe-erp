from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Any, List, Optional, Union

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.enums import ContractType, RegistrationStatus
from models.schemas.exceptions import (
    MTEmploymentUpdateRequestInvalidCertifications,
    MTEmploymentUpdateRequestInvalidContractType,
    MTEmploymentUpdateRequestInvalidFieldEmployee,
    MTInvalidEmploymentUpdateRequestException,
    MTInvalidStatusUpdateRequestException,
    MTStatusUpdateRequestInvalidStatus,
)
from models.schemas.requests.hca.employment_update_request import EmploymentUpdateRequest
from models.schemas.requests.hca.hca_profile_update_request import (
    HcaProfileUpdateRequest,
)
from models.schemas.requests.customers.status_update_request import StatusUpdateRequest


class TestEmploymentUpdateRequest:
    """Tests for the payload a manager may send about an assistant."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_contract_alone_is_enough(self) -> None:
        """Certifications default to none, which is a real state."""
        payload = EmploymentUpdateRequest(contract_type=ContractType.CDI)

        assert payload.contract_type is ContractType.CDI
        assert payload.certifications == []
        assert payload.field_employee is True

    def test_certifications_are_parsed(self) -> None:
        """A qualification arrives as a model, not a mapping."""
        payload = EmploymentUpdateRequest(
            contract_type=ContractType.CDD,
            certifications=[
                {
                    "name": "DEAES",
                    "issuer": "Ministere du Travail",
                    "obtained_on": "2024-06-01",
                }
            ],
        )

        assert payload.certifications[0].name == "DEAES"
        assert payload.certifications[0].obtained_on == date(2024, 6, 1)

    # ------------------------------------------------------------------ #
    #  The shape is the permission
    # ------------------------------------------------------------------ #

    def test_it_carries_only_the_three_permitted_fields(self) -> None:
        """A manager may change the contract, the qualifications and the rounds.

        Notes:
            **This test is the rule.** "A manager may modify only the contract
            type, the certifications and whether this person goes out" is
            enforced by this model's shape rather than by a check somewhere
            that could be forgotten — so a field added here silently widens
            what a manager may do, and this assertion is what refuses to let
            that happen quietly.
        """
        assert set(EmploymentUpdateRequest.model_fields) == {
            "contract_type",
            "certifications",
            "field_employee",
        }

    def test_an_assistant_cannot_reach_this_field_at_all(self) -> None:
        """``field_employee`` is absent from the assistant's own edit payload.

        Notes:
            **This placement is the rule that an assistant may not withdraw
            themselves from the workforce.** A manager or an administrator
            reaches this model for anybody, including themselves; an assistant
            reaches only
            :class:`~models.schemas.requests.hca.hca_profile_update_request.HcaProfileUpdateRequest`,
            which carries no such field. Expressing it as a check inside a
            service would be one more thing to remember; expressing it as a
            field that is simply not there cannot be forgotten.
        """
        assert "field_employee" not in HcaProfileUpdateRequest.model_fields

    def test_an_unrelated_field_does_not_ride_along(self) -> None:
        """A home address in the payload changes nothing.

        Notes:
            Pydantic ignores unknown fields by default, so this passes rather
            than raises — what matters is that the value never reaches the
            model, and so can never reach the assistant's record.
        """
        payload = EmploymentUpdateRequest(
            contract_type=ContractType.CDI,
            address={"street": "Somewhere else", "postal_code": "75001"},
        )

        assert not hasattr(payload, "address")

    # ------------------------------------------------------------------ #
    #  field_employee validation
    # ------------------------------------------------------------------ #

    def test_the_rounds_flag_can_be_cleared(self) -> None:
        """A manager may take somebody off the rounds without touching anything else."""
        payload = EmploymentUpdateRequest(
            contract_type=ContractType.CDI, field_employee=False
        )
        assert payload.field_employee is False

    def test_an_omitted_flag_leaves_them_on_the_rounds(self) -> None:
        """A payload written before the field existed still means "schedulable"."""
        payload = EmploymentUpdateRequest(
            contract_type=ContractType.CDI, field_employee=None
        )
        assert payload.field_employee is True

    @pytest.mark.parametrize(
        "invalid_flag",
        [
            pytest.param("false", id="Invalid - string false"),
            pytest.param("true", id="Invalid - string true"),
            pytest.param(0, id="Invalid - int"),
            pytest.param([], id="Invalid - list"),
        ],
    )
    def test_an_invalid_rounds_flag_is_refused(self, invalid_flag: Any) -> None:
        """The flag is a boolean, never a truthy string.

        Notes:
            ``"false"`` is truthy in Python, so coercing it would put somebody
            back on a round the agency had taken them off.
        """
        with pytest.raises(MTEmploymentUpdateRequestInvalidFieldEmployee):
            EmploymentUpdateRequest(
                contract_type=ContractType.CDI, field_employee=invalid_flag
            )

    # ------------------------------------------------------------------ #
    #  contract_type validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("cdi", id="Valid - cdi"),
            pytest.param("cdd", id="Valid - cdd"),
            pytest.param("interim", id="Valid - interim"),
            pytest.param("internship", id="Valid - internship"),
            pytest.param(ContractType.CDI, id="Valid - already an enum"),
        ],
    )
    def test_a_known_contract_is_accepted(
        self, value: Union[str, ContractType]
    ) -> None:
        """Every contract the agency uses is accepted.

        Args:
            value (Union[str, ContractType]): The contract to check.
        """
        assert EmploymentUpdateRequest(contract_type=value).contract_type

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("permanent", id="Invalid - not a member"),
            pytest.param("CDI", id="Invalid - wrong case"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - missing"),
        ],
    )
    def test_an_unknown_contract_is_refused(self, value: Optional[str]) -> None:
        """An unrecognised contract raises this model's own exception.

        Args:
            value (Optional[str]): The rejected value.
        """
        with pytest.raises(MTEmploymentUpdateRequestInvalidContractType):
            EmploymentUpdateRequest(contract_type=value)

    def test_there_is_no_default_contract(self) -> None:
        """An empty body cannot silently move somebody onto a contract.

        Notes:
            A wholly absent field is refused by Pydantic before any validator
            runs, so this raises ``ValidationError`` rather than the model's
            own exception. Both answer 422 — the point being pinned is that
            there is no default, not which of the two paths refuses it.
        """
        with pytest.raises(ValidationError):
            EmploymentUpdateRequest()

    # ------------------------------------------------------------------ #
    #  certifications validation
    # ------------------------------------------------------------------ #

    def test_a_null_certification_list_reads_as_empty(self) -> None:
        """Omitting the list means "none held", not an error."""
        payload = EmploymentUpdateRequest(
            contract_type=ContractType.CDI, certifications=None
        )

        assert payload.certifications == []

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param({"name": "DEAES"}, id="Invalid - a single object"),
            pytest.param("DEAES", id="Invalid - a bare string"),
            pytest.param(7, id="Invalid - a number"),
        ],
    )
    def test_a_non_list_of_certifications_is_refused(self, value: object) -> None:
        """A malformed list raises rather than being coerced.

        Args:
            value (object): The rejected value.
        """
        with pytest.raises(MTEmploymentUpdateRequestInvalidCertifications):
            EmploymentUpdateRequest(
                contract_type=ContractType.CDI, certifications=value
            )

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception",
        [
            pytest.param(
                MTEmploymentUpdateRequestInvalidContractType, id="contract type"
            ),
            pytest.param(
                MTEmploymentUpdateRequestInvalidCertifications, id="certifications"
            ),
        ],
    )
    def test_every_leaf_shares_one_base(self, exception: type) -> None:
        """One except clause catches everything this model raises.

        Args:
            exception (type): The leaf exception to check.

        Notes:
            The 422 handler is registered against the base, so a leaf outside
            the family would escape as a 500.
        """
        assert issubclass(exception, MTInvalidEmploymentUpdateRequestException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_it_round_trips(self) -> None:
        """A dumped payload rebuilds identically."""
        payload = EmploymentUpdateRequest(
            contract_type=ContractType.INTERIM,
            certifications=[{"name": "SST", "issuer": "INRS"}],
        )
        rebuilt = EmploymentUpdateRequest.model_validate(payload.model_dump())

        assert rebuilt.contract_type is ContractType.INTERIM
        certifications: List[str] = [item.name for item in rebuilt.certifications]
        assert certifications == ["SST"]


class TestStatusUpdateRequest:
    """Tests for the payload activating or stopping a customer."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("active", id="Valid - active"),
            pytest.param("stopped", id="Valid - stopped"),
            pytest.param(RegistrationStatus.ACTIVE, id="Valid - already an enum"),
        ],
    )
    def test_a_known_status_is_accepted(
        self, value: Union[str, RegistrationStatus]
    ) -> None:
        """Both registration states are accepted.

        Args:
            value (Union[str, RegistrationStatus]): The status to check.
        """
        assert StatusUpdateRequest(registration_status=value).registration_status

    def test_it_carries_only_the_status(self) -> None:
        """Nothing else can ride along with a status change."""
        assert set(StatusUpdateRequest.model_fields) == {"registration_status"}

    # ------------------------------------------------------------------ #
    #  registration_status validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("suspended", id="Invalid - not a member"),
            pytest.param("ACTIVE", id="Invalid - wrong case"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - missing"),
        ],
    )
    def test_an_unknown_status_is_refused(self, value: Optional[str]) -> None:
        """An unrecognised status raises this model's own exception.

        Args:
            value (Optional[str]): The rejected value.
        """
        with pytest.raises(MTStatusUpdateRequestInvalidStatus):
            StatusUpdateRequest(registration_status=value)

    def test_there_is_no_default_status(self) -> None:
        """An empty body cannot silently stop a customer.

        Notes:
            As above: an absent field is Pydantic's refusal, an *invalid* one
            is the model's. Both are 422.
        """
        with pytest.raises(ValidationError):
            StatusUpdateRequest()

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    def test_the_leaf_shares_the_base(self) -> None:
        """One except clause catches everything this model raises."""
        assert issubclass(
            MTStatusUpdateRequestInvalidStatus, MTInvalidStatusUpdateRequestException
        )

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_it_round_trips(self) -> None:
        """A dumped payload rebuilds identically."""
        payload = StatusUpdateRequest(registration_status=RegistrationStatus.STOPPED)
        rebuilt = StatusUpdateRequest.model_validate(payload.model_dump())

        assert rebuilt.registration_status is RegistrationStatus.STOPPED
