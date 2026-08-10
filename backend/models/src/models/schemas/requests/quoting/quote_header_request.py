from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.schemas.exceptions import (
    MTQuoteHeaderRequestInvalidAutoRenew,
    MTQuoteHeaderRequestInvalidCustomer,
    MTQuoteHeaderRequestInvalidDate,
    MTQuoteHeaderRequestInvalidReference,
    MTQuoteHeaderRequestInvalidValidity,
)


class QuoteHeaderRequest(BaseModel):
    """Everything about a quote except its lines and its status.

    Attributes:
        reference (str): The human-facing quote number.
        customer_id (str): Who the offer is addressed to.
        issued_on (Optional[date]): When it was issued.
        valid_until (Optional[date]): The last day it may be accepted.
        auto_renew (bool): Whether it renews itself when it runs out.

    Notes:
        - **The lines are not here, and neither is the status.** The lines have
          their own route because replacing them reprices the quote, and the
          status has one transition per verb — send, validate, refuse, accept —
          each with its own rules about who may do it and what it means. A
          status that could be set directly would let an operator mark a quote
          accepted without the customer having accepted anything.
        - **Changing the customer moves the work.** An accepted quote reassigned
          to somebody else moves every visit on it to a different address, which
          the next planning run will route to. That is occasionally exactly what
          is wanted — a quote written against the wrong record — and it is
          never something to do without noticing, so the service logs it.
    """

    reference: str = Field(description="The human-facing quote number.")
    customer_id: str = Field(description="Who the offer is addressed to.")
    issued_on: Optional[date] = Field(
        default=None, description="When the quote was issued."
    )
    valid_until: Optional[date] = Field(
        default=None, description="The last day it may be accepted."
    )
    auto_renew: bool = Field(
        default=False, description="Whether it renews itself when it runs out."
    )

    ############################
    #    Validation Methods    #
    ############################

    @field_validator("reference", mode="before")
    def validate_reference(cls, value: Union[str, None]) -> str:
        """Validates that the reference is readable text.

        Args:
            value (Union[str, None]): Raw reference.

        Returns:
            str: The trimmed reference.

        Raises:
            MTQuoteHeaderRequestInvalidReference: If it is not a non-empty
                string.

        Notes:
            This is what a customer quotes back on the telephone and what the
            planning report groups by, so a blank one leaves both without a
            handle. Uniqueness is not checked here — this payload cannot see
            the other quotes — but the storage layer's own constraint does.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteHeaderRequestInvalidReference(
                f"Invalid reference: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("customer_id", mode="before")
    def validate_customer_id(cls, value: Union[str, None]) -> str:
        """Validates that the quote is addressed to somebody.

        Args:
            value (Union[str, None]): Raw customer identifier.

        Returns:
            str: The trimmed identifier.

        Raises:
            MTQuoteHeaderRequestInvalidCustomer: If it is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteHeaderRequestInvalidCustomer(
                f"Invalid customer_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("issued_on", "valid_until", mode="before")
    def validate_date(cls, value: Union[str, date, None]) -> Union[str, date, None]:
        """Validates that a date is a date, or absent.

        Args:
            value (Union[str, date, None]): Raw date.

        Returns:
            Union[str, date, None]: The value, for the field type to parse.

        Raises:
            MTQuoteHeaderRequestInvalidDate: If it is neither a date, an ISO
                string nor absent.

        Notes:
            Both are genuinely optional. A quote drafted this morning has not
            been issued, and one written for an open-ended arrangement has no
            expiry — an empty box means "not yet" rather than an error.
        """
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            if not value.strip():
                return None
            try:
                date.fromisoformat(value)
            except ValueError:
                raise MTQuoteHeaderRequestInvalidDate(
                    f"Invalid date: {value!r}. Must be an ISO date."
                ) from None
            return value
        raise MTQuoteHeaderRequestInvalidDate(
            f"Invalid date: {value!r}. Must be an ISO date or absent."
        )

    @field_validator("auto_renew", mode="before")
    def validate_auto_renew(cls, value: Union[bool, str, None]) -> bool:
        """Validates that ``auto_renew`` is a boolean.

        Args:
            value (Union[bool, str, None]): Raw flag.

        Returns:
            bool: The validated flag.

        Raises:
            MTQuoteHeaderRequestInvalidAutoRenew: If it is not a boolean.
        """
        if value is None:
            return False
        if not isinstance(value, bool):
            raise MTQuoteHeaderRequestInvalidAutoRenew(
                f"Invalid auto_renew: {value!r}. Must be true or false."
            )
        return value

    @model_validator(mode="after")
    def check_validity(self) -> QuoteHeaderRequest:
        """Ensure a quote cannot expire before it is issued.

        Returns:
            QuoteHeaderRequest: ``self`` for chaining.

        Raises:
            MTQuoteHeaderRequestInvalidValidity: If ``valid_until`` falls
                before ``issued_on``.

        Notes:
            Checked here rather than left to the reader, because the pair is
            only wrong together. Either date alone is fine, and a quote that
            expired before it existed is refused by nothing else — it would
            simply never be acceptable, with no explanation on any screen.
        """
        if (
            self.issued_on is not None
            and self.valid_until is not None
            and self.valid_until < self.issued_on
        ):
            raise MTQuoteHeaderRequestInvalidValidity(
                f"Invalid validity: a quote issued on {self.issued_on} cannot "
                f"expire on {self.valid_until}."
            )
        return self
