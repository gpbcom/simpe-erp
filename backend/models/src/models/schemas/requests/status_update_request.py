from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import RegistrationStatus
from models.schemas.exceptions import MTStatusUpdateRequestInvalidStatus


class StatusUpdateRequest(BaseModel):
    """The payload activating or stopping a customer.

    Attributes:
        registration_status (RegistrationStatus): The status to set.

    Notes:
        One field, like every other targeted update in this API: stopping a
        customer is what a manager does without touching anything else, and a
        route accepting a whole customer would let a stale payload clobber
        their address on the way past.
    """

    registration_status: RegistrationStatus = Field(
        description="The registration status to set."
    )

    @field_validator("registration_status", mode="before")
    def validate_registration_status(
        cls, value: Union[str, RegistrationStatus, None]
    ) -> RegistrationStatus:
        """Validates that ``registration_status`` is a known status.

        Args:
            value (Union[str, RegistrationStatus, None]): Raw value.

        Returns:
            RegistrationStatus: The coerced status.

        Raises:
            MTStatusUpdateRequestInvalidStatus: If ``value`` is not a known
                registration status.
        """
        if isinstance(value, RegistrationStatus):
            return value
        try:
            return RegistrationStatus(value)
        except ValueError:
            raise MTStatusUpdateRequestInvalidStatus(
                f"Invalid registration_status: {value!r}. Must be one of: "
                f"{', '.join(RegistrationStatus.values())}."
            ) from None
