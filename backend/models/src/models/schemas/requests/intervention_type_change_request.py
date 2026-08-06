from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTInterventionTypeChangeRequestInvalidTypeId


class InterventionTypeChangeRequest(BaseModel):
    """The payload selling a scheduled visit as a different service.

    Attributes:
        intervention_type_id (str): The catalogue entry the visit should be
            sold as.

    Notes:
        One field, and no amounts. What the visit now costs is the server's
        answer, not the caller's: the rate comes from the catalogue, the
        surcharge from the day it falls on and the VAT from the category, and a
        figure sent from a screen would be a second answer that disagrees with
        the stored one the first time a rate changes.
    """

    intervention_type_id: str = Field(
        description="The catalogue entry the visit should be sold as."
    )

    @field_validator("intervention_type_id", mode="before")
    def validate_intervention_type_id(cls, value: Optional[str]) -> str:
        """Validates that ``intervention_type_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``intervention_type_id`` value.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTInterventionTypeChangeRequestInvalidTypeId: If ``value`` is
                missing, not a string, or blank.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionTypeChangeRequestInvalidTypeId(
                f"Invalid intervention_type_id: {value!r}. Must be a non-empty "
                f"string naming a catalogue entry."
            )
        return value.strip()
