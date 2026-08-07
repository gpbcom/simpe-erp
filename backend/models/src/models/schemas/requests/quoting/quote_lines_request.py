from __future__ import annotations

# Standard library imports
from typing import List

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.quoting.quote_line import QuoteLine
from models.schemas.exceptions import MTQuoteLinesRequestInvalidLines


class QuoteLinesRequest(BaseModel):
    """The payload replacing a draft quote's services.

    Attributes:
        lines (List[QuoteLine]): The services that replace the stored ones.

    Notes:
        - **The shape of this model is the permission**, and here it merely makes
          true what the route already promised. Its docstring said "only the lines
          are taken from the body", and the service did indeed ignore the rest —
          but the body was a whole :class:`~models.quoting.quote.Quote`, so the
          rest could be *sent*, and a reader had to trust a comment rather than a
          type. Now there is nothing else to send.
        - That distinction stopped being cosmetic once a quote carried its agency:
          a body able to name one would let an edit move a quote between agencies,
          which is a change no repricing route should be able to make.
        - Replacement rather than a patch. A quote's services are read as a whole
          — the weekly aggregates are recomputed from all of them — so a partial
          edit would have to say what it left alone, and every caller would have
          to get that right.
    """

    lines: List[QuoteLine] = Field(
        default_factory=list,
        description="The services that replace the stored ones.",
    )

    @field_validator("lines", mode="before")
    def validate_lines(cls, value: JsonValue) -> JsonValue:
        """Validates that ``lines`` is a list, when it is sent at all.

        Args:
            value (JsonValue): Raw ``lines`` value.

        Returns:
            JsonValue: The value handed back for the field type to parse.

        Raises:
            MTQuoteLinesRequestInvalidLines: If ``value`` is neither ``None``
                nor a list.

        Notes:
            **An empty list is a real edit**, and means the quote now offers
            nothing — which is how the last line is removed. It is not read as
            "leave the lines alone": a route that could not empty a quote would
            leave a line nobody could delete.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTQuoteLinesRequestInvalidLines(
                f"Invalid lines: {value!r}. Must be a list or None."
            )
        return value
