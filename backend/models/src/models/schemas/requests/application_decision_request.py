from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import ContractType
from models.schemas.exceptions import (
    MTApplicationDecisionRequestInvalidContractType,
)


class ApplicationDecisionRequest(BaseModel):
    """The payload approving an assistant's application.

    Attributes:
        contract_type (ContractType): The contract they are taken on under.

    Notes:
        The contract type comes from the approver, not from the application.
        An applicant may say what they hope for; what they are employed under
        is the agency's decision, and reading it off the application would let
        an unauthenticated payload set an employment term.
    """

    contract_type: ContractType = Field(
        description="The contract the applicant is taken on under."
    )

    @field_validator("contract_type", mode="before")
    def validate_contract_type(
        cls, value: Union[str, ContractType, None]
    ) -> ContractType:
        """Validates that ``contract_type`` is a known contract.

        Args:
            value (Union[str, ContractType, None]): Raw contract value.

        Returns:
            ContractType: The coerced contract type.

        Raises:
            MTApplicationDecisionRequestInvalidContractType: If ``value`` is
                not a known contract type.

        Notes:
            No default. Approving somebody onto whichever contract happens to
            be first in the enumeration is not a decision anybody made.
        """
        if isinstance(value, ContractType):
            return value
        try:
            return ContractType(value)
        except ValueError:
            raise MTApplicationDecisionRequestInvalidContractType(
                f"Invalid contract_type: {value!r}. Must be one of: "
                f"{', '.join(ContractType.values())}."
            ) from None
