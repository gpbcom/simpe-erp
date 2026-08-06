from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTQuoteInterruptionRequestInvalidDay


class QuoteInterruptionRequest(BaseModel):
    """The payload ending a running arrangement early.

    Attributes:
        last_day (date): The final day the arrangement is delivered.

    Notes:
        **Inclusive.** ``last_day`` is delivered; the day after it is not. A
        family cancelling "from the 15th" means the 15th is the last visit, and
        reading it as the first cancelled day takes away a visit somebody is
        expecting to receive.

        The field is required and has no default. "Interrupt this quote" with
        no date could only mean today, and today is rarely what anybody means:
        an arrangement is usually ended with notice, on a date agreed with the
        family.
    """

    last_day: date = Field(description="The final day the arrangement runs.")

    @field_validator("last_day", mode="before")
    def validate_last_day(cls, value: Union[str, date, None]) -> Union[str, date]:
        """Validates that ``last_day`` is present before it is parsed.

        Args:
            value (Union[str, date, None]): Raw ``last_day`` value.

        Returns:
            Union[str, date]: The value, for the field type to parse.

        Raises:
            MTQuoteInterruptionRequestInvalidDay: If ``value`` is missing or
                blank.

        Notes:
            Whether the day falls inside the arrangement is not checked here.
            That depends on the quote, which this payload cannot see, so
            :class:`~models.quoting.quote.Quote` refuses an impossible one and
            the route answers 422 either way.
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            raise MTQuoteInterruptionRequestInvalidDay(
                f"Invalid last_day: {value!r}. Must be a date."
            )
        return value
