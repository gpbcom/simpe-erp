from __future__ import annotations

# Standard library imports
from typing import List, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.enums import ContractType
from models.people.hca.certification import Certification
from models.schemas.exceptions import (
    MTEmploymentUpdateRequestInvalidCertifications,
    MTEmploymentUpdateRequestInvalidContractType,
    MTEmploymentUpdateRequestInvalidFieldEmployee,
)


class EmploymentUpdateRequest(BaseModel):
    """The payload changing what a manager is allowed to change on an assistant.

    Attributes:
        contract_type (ContractType): The employment contract now held.
        certifications (List[Certification]): The qualifications now held.
        field_employee (bool): Whether the person may be placed on an
            intervention planning.

    Notes:
        - **The shape of this model is the permission.** A manager may change
          an assistant's contract type, their certifications and whether they
          go out on rounds, and nothing else — that rule is enforced by there
          being no manager-reachable route that accepts a fuller payload,
          rather than by a check somewhere that could be forgotten. The
          contact details, the home address and the declared availability are
          unreachable from here.
        - ``field_employee`` lives here rather than on the assistant's own
          self-service request, and that placement *is* the rule that an
          assistant may not withdraw themselves from the workforce. A manager
          or an administrator reaches this model for anybody — including
          themselves, since the route takes an identifier and they hold the
          role — while an assistant reaches no route that carries the field at
          all. Expressing it as a check inside a service would be one more
          thing to remember; expressing it as a field that is simply absent
          from the other payload cannot be forgotten.
    """

    contract_type: ContractType = Field(description="The employment contract.")
    certifications: List[Certification] = Field(
        default_factory=list, description="The qualifications now held."
    )
    field_employee: bool = Field(
        default=True,
        description="Whether the person may be placed on a planning.",
    )

    @field_validator("contract_type", mode="before")
    def validate_contract_type(
        cls, value: Union[str, ContractType, None]
    ) -> ContractType:
        """Validates that ``contract_type`` is a known contract.

        Args:
            value (Union[str, ContractType, None]): Raw ``contract_type``.

        Returns:
            ContractType: The coerced contract type.

        Raises:
            MTEmploymentUpdateRequestInvalidContractType: If ``value`` is not a
                known contract type.

        Notes:
            There is no default. An employment change must state the contract
            it grants, or an empty body would quietly move somebody onto
            whichever contract happened to be first in the enumeration.
        """
        if isinstance(value, ContractType):
            return value
        try:
            return ContractType(value)
        except ValueError:
            raise MTEmploymentUpdateRequestInvalidContractType(
                f"Invalid contract_type: {value!r}. Must be one of: "
                f"{', '.join(ContractType.values())}."
            ) from None

    @field_validator("field_employee", mode="before")
    def validate_field_employee(cls, value: Union[bool, str, int, None]) -> bool:
        """Validates that ``field_employee`` is a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw ``field_employee`` value.
                ``None`` falls back to ``True``.

        Returns:
            bool: The validated flag.

        Raises:
            MTEmploymentUpdateRequestInvalidFieldEmployee: If ``value`` is
                neither ``None`` nor a boolean.

        Notes:
            An omitted flag means "still on the rounds", which matches the
            model's own default and is the safe reading of a payload written
            before this field existed. A *malformed* one is refused rather than
            coerced: ``"false"`` is truthy in Python, and quietly reading it as
            "yes" would put somebody back on a round the agency had taken them
            off.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTEmploymentUpdateRequestInvalidFieldEmployee(
                f"Invalid field_employee: {value!r}. Must be true or false."
            )
        return value

    @field_validator("certifications", mode="before")
    def validate_certifications(cls, value: JsonValue) -> JsonValue:
        """Validates that ``certifications`` is a list.

        Args:
            value (JsonValue): Raw ``certifications`` value.

        Returns:
            JsonValue: The value, unchanged, for the field type to parse.

        Raises:
            MTEmploymentUpdateRequestInvalidCertifications: If ``value`` is
                neither ``None`` nor a list.

        Notes:
            An omitted list means "no qualifications", which is a real state —
            a new assistant may hold none. A *malformed* one is refused, since
            a single object where a list is expected would otherwise be
            reported as a type error with no indication of which field.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTEmploymentUpdateRequestInvalidCertifications(
                f"Invalid certifications: {value!r}. Must be a list."
            )
        return value
