from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import BillStatus
from models.schemas.exceptions import MTBillStatusRequestInvalidStatus


class BillStatusRequest(BaseModel):
    """The payload moving a bill along its commercial lifecycle.

    Attributes:
        status (BillStatus): The status the bill is being moved to.

    Notes:
        - The payload names only the destination. Whether the move is legal is
          decided against the bill's *current* status by
          :meth:`~models.enums.BillStatus.can_move_to`, which the caller cannot
          be trusted to have read — a screen showing a stale row would otherwise
          send a transition that was legal when it was rendered.
        - There is no reason field. Who moved it and when are recorded on the
          bill; why is a conversation, not a column, and a free-text field on a
          financial record is one nobody fills in truthfully.
    """

    status: BillStatus = Field(
        description="The status the bill is being moved to.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("status", mode="before")
    def validate_status(cls, value: Union[str, BillStatus, None]) -> BillStatus:
        """Validates that ``status`` names a known bill status.

        Args:
            value (Union[str, BillStatus, None]): Raw status.

        Returns:
            BillStatus: The coerced status.

        Raises:
            MTBillStatusRequestInvalidStatus: If ``value`` is missing or is not
                a known status.

        Notes:
            No default. A status change is the one request whose whole content
            is the status, so a missing one is an empty instruction rather than
            something to guess at.
        """
        if value is None:
            raise MTBillStatusRequestInvalidStatus(
                "Invalid status: a destination status is required."
            )
        if isinstance(value, BillStatus):
            return value
        try:
            return BillStatus(value)
        except ValueError:
            raise MTBillStatusRequestInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(BillStatus.values())}."
            ) from None
