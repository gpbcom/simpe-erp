from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTBillAcceptedRequestInvalidId


class BillAcceptedRequest(BaseModel):
    """The payload announcing that a validated bill is ready to be sent.

    Attributes:
        bill_id (str): The bill a manager approved.

    Notes:
        Carries an identifier and nothing else, exactly as the planning webhook
        does. The endpoint re-reads the bill, so a payload carrying its amounts
        would be a second copy of the invoice travelling over the wire — one that
        could disagree with the stored one and decide what a customer is emailed.
    """

    bill_id: str = Field(description="The bill a manager approved.")

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("bill_id", mode="before")
    def validate_bill_id(cls, value: Optional[str]) -> str:
        """Validates that ``bill_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTBillAcceptedRequestInvalidId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillAcceptedRequestInvalidId(
                f"Invalid bill_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()
