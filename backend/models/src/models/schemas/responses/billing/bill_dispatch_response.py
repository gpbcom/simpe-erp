from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTBillDispatchResponseInvalidId


class BillDispatchResponse(BaseModel):
    """What the bill webhook reports about sending one invoice.

    Attributes:
        bill_id (str): The bill the dispatch was for.
        sent (bool): Whether the customer received it.

    Notes:
        - The flag is what actually happened, not what was attempted. A bill
          whose delivery failed answers ``False`` and stays awaiting its
          approval's effect, so a manager reading the list sees an invoice
          approved but not yet out — which is the truth, and is actionable.
        - A failed delivery is **not** an error response. The invoice is written,
          numbered and downloadable; the customer's mail server being unreachable
          is not a reason to answer a 5xx and have the announcement retried until
          it dead-letters.
    """

    bill_id: str = Field(description="The bill the dispatch was for.")
    sent: bool = Field(
        default=False,
        description="Whether the customer received it.",
    )

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
            MTBillDispatchResponseInvalidId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillDispatchResponseInvalidId(
                f"Invalid bill_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()
