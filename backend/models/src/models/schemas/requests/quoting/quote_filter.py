from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Type, Union

# Third-party imports
from pydantic import Field, field_validator

# First-party imports
from models.base.entity_filter import EntityFilter
from models.base.exceptions import MTInvalidEntityFilterException
from models.enums import QuoteStatus
from models.schemas.exceptions import (
    MTQuoteFilterInvalidFlag,
    MTQuoteFilterInvalidFragment,
    MTQuoteFilterInvalidStatus,
)


class QuoteFilter(EntityFilter):
    """What narrows the quote list on the way out of the API.

    Attributes:
        search (Optional[str]): Fragment matched against the reference.
        status (Optional[QuoteStatus]): Restrict to one quote status.
        customer_id (Optional[str]): Restrict to one customer's quotes.
        authored_by (Optional[str]): Restrict to one author's quotes.
        reference (Optional[str]): Fragment matched against the reference.
        is_ongoing (Optional[bool]): Restrict to arrangements currently being
            delivered, or to those that are not.
        auto_renew (Optional[bool]): Restrict to quotes that renew themselves.

    Notes:
        - ``customer_id`` and ``authored_by`` are **identifiers, not
          fragments.** A quote list narrowed to "customers whose id contains
          ``7``" is not a question anybody asks, and matching an identifier
          loosely is how one customer's arrangements appear under another's
          name.
        - ``is_ongoing`` is derived rather than stored: a quote is being
          delivered when it is accepted and has not been interrupted or run
          past its end. Keeping it a filter rather than a column means the
          answer cannot drift from what the quote screen calls ongoing.
        - ``search`` and ``reference`` overlap deliberately, as they do on the
          customer filter: one is the box somebody types into without deciding
          what it is, the other is for when they have decided.
    """

    INVALID_FRAGMENT: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTQuoteFilterInvalidFragment
    )
    INVALID_FLAG: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTQuoteFilterInvalidFlag
    )

    search: Optional[str] = Field(
        default=None, description="Fragment matched against the reference."
    )
    status: Optional[QuoteStatus] = Field(
        default=None, description="Restrict to one quote status."
    )
    customer_id: Optional[str] = Field(
        default=None, description="Restrict to one customer's quotes."
    )
    authored_by: Optional[str] = Field(
        default=None, description="Restrict to one author's quotes."
    )
    reference: Optional[str] = Field(
        default=None, description="Fragment of the quote reference."
    )
    is_ongoing: Optional[bool] = Field(
        default=None,
        description="Whether the arrangement is currently being delivered.",
    )
    auto_renew: Optional[bool] = Field(
        default=None, description="Whether the quote renews itself."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Union[str, QuoteStatus, None]
    ) -> Optional[QuoteStatus]:
        """Validates that ``status`` is absent or a known quote status.

        Args:
            value (Union[str, QuoteStatus, None]): Raw status value.

        Returns:
            Optional[QuoteStatus]: The coerced status, or ``None``.

        Raises:
            MTQuoteFilterInvalidStatus: If ``value`` is neither empty nor a
                known quote status.

        Notes:
            An empty string is "not applied" rather than a rejection: a select
            reset to its blank option submits ``""``, and answering 422 for it
            would put an error where a quote list belongs.
        """
        if value is None or value == "":
            return None
        if isinstance(value, QuoteStatus):
            return value
        try:
            return QuoteStatus(value)
        except ValueError:
            raise MTQuoteFilterInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(QuoteStatus.values())}."
            ) from None

    @field_validator(
        "search", "customer_id", "authored_by", "reference", mode="before"
    )
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a text filter is absent or a usable fragment.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when empty.

        Raises:
            MTQuoteFilterInvalidFragment: If ``value`` is neither ``None`` nor
                a string.
        """
        return cls.validate_fragment(value)

    @field_validator("is_ongoing", "auto_renew", mode="before")
    def validate_flags(cls, value: Union[bool, str, int, None]) -> Optional[bool]:
        """Validates that a three-state flag is absent or a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw flag value.

        Returns:
            Optional[bool]: The flag, or ``None`` when unset.

        Raises:
            MTQuoteFilterInvalidFlag: If ``value`` is neither ``None`` nor a
                boolean.
        """
        return cls.validate_flag(value)
