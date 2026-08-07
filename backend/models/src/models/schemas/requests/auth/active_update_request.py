from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTActiveUpdateRequestInvalidIsActive


class ActiveUpdateRequest(BaseModel):
    """The payload enabling or disabling sign-in for an account.

    Attributes:
        is_active (bool): Whether sign-in is permitted.
    """

    is_active: bool = Field(description="Whether sign-in is permitted.")

    @field_validator("is_active", mode="before")
    def validate_is_active(cls, value: Union[bool, str, int, None]) -> bool:
        """Validates that ``is_active`` is a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw ``is_active`` value.

        Returns:
            bool: The validated flag.

        Raises:
            MTActiveUpdateRequestInvalidIsActive: If ``value`` is not a
                boolean.

        Notes:
            Strings and integers are rejected rather than coerced. Pydantic
            would happily read ``0`` or ``"false"`` as ``False``, but so would
            it read ``"no"`` as an error and ``"False"`` inconsistently across
            versions — for a flag that locks people out of the system, an
            explicit boolean is the only safe input.
        """
        if not isinstance(value, bool):
            raise MTActiveUpdateRequestInvalidIsActive(
                f"Invalid is_active: {value!r}. Must be true or false."
            )
        return value
