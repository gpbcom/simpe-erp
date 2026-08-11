from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTBillPaidRequestInvalidId


class BillPaidRequest(BaseModel):
    """The payload announcing that an invoice has been collected.

    Attributes:
        bill_id (str): The bill that was settled.

    Notes:
        - Carries an identifier and nothing else, exactly as its approval twin
          does. The endpoint re-reads the invoice, so amounts on the wire would
          be a second copy of the document — one that could disagree with the
          stored one and decide what is declared to the tax authority.
        - **A separate payload from the approval one even though the shape is
          identical**, because the two announce different obligations. Sharing a
          class would leave one docstring describing both, and the next person
          reading it could not tell which endpoint they were looking at.
    """

    bill_id: str = Field(description="The bill that was settled.")

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("bill_id", mode="before")
    def validate_bill_id(cls, value: Optional[str]) -> str:
        """Validates that ``bill_id`` is a non-empty identifier.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTBillPaidRequestInvalidId: If ``value`` is not a non-empty string.
        """
        if value is None or not isinstance(value, str) or not value.strip():
            raise MTBillPaidRequestInvalidId(
                f"Invalid bill_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()
