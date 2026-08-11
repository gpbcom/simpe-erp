from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import ClassVar, Optional, Type, Union

# Third-party imports
from pydantic import Field, field_validator

# First-party imports
from models.base.entity_filter import EntityFilter
from models.base.exceptions import MTInvalidEntityFilterException
from models.enums import BillStatus
from models.schemas.exceptions import (
    MTBillFilterInvalidDate,
    MTBillFilterInvalidFlag,
    MTBillFilterInvalidFragment,
    MTBillFilterInvalidStatus,
)


class BillFilter(EntityFilter):
    """What narrows the bill list on the way out of the API.

    Attributes:
        search (Optional[str]): Fragment matched against the invoice number.
        number (Optional[str]): Fragment matched against the invoice number.
        customer_id (Optional[str]): Restrict to one customer's invoices.
        status (Optional[BillStatus]): Restrict to one commercial status.
        is_sent (Optional[bool]): Restrict to invoices the customer has been
            sent, or to those they have not.
        period_start (Optional[date]): Only invoices whose window starts on or
            after this day.
        period_end (Optional[date]): Only invoices whose window ends on or
            before this day.

    Notes:
        - ``customer_id`` is an **identifier, not a fragment**. "Customers whose
          id contains 7" is not a question anybody asks, and matching an
          identifier loosely is how one customer's invoices appear under
          another's name — which on a financial document is worse than on a list.
        - ``is_sent`` reads the timestamp rather than the status, and the two can
          disagree on purpose: a bill a manager pushed to awaiting-payment by
          hand while the mail server was down is awaited but was never sent.
          Somebody chasing "what has actually gone out" needs the first answer.
        - The period bounds narrow by the **window billed**, not by the invoice
          date. An agency asking "show me March" means the care delivered in
          March, whatever day the invoice for it was written.
    """

    INVALID_FRAGMENT: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTBillFilterInvalidFragment
    )
    INVALID_FLAG: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTBillFilterInvalidFlag
    )

    search: Optional[str] = Field(
        default=None, description="Fragment matched against the invoice number."
    )
    number: Optional[str] = Field(
        default=None, description="Fragment of the invoice number."
    )
    customer_id: Optional[str] = Field(
        default=None, description="Restrict to one customer's invoices."
    )
    status: Optional[BillStatus] = Field(
        default=None, description="Restrict to one commercial status."
    )
    is_sent: Optional[bool] = Field(
        default=None,
        description="Whether the customer has been sent the invoice.",
    )
    period_start: Optional[date] = Field(
        default=None,
        description="Only invoices whose window starts on or after this day.",
    )
    period_end: Optional[date] = Field(
        default=None,
        description="Only invoices whose window ends on or before this day.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Union[str, BillStatus, None]
    ) -> Optional[BillStatus]:
        """Validates that ``status`` is absent or a known bill status.

        Args:
            value (Union[str, BillStatus, None]): Raw status value.

        Returns:
            Optional[BillStatus]: The coerced status, or ``None``.

        Raises:
            MTBillFilterInvalidStatus: If ``value`` is neither empty nor a known
                bill status.

        Notes:
            An empty string is "not applied" rather than a rejection: a select
            reset to its blank option submits ``""``, and answering 422 for it
            would put an error where a bill list belongs.
        """
        if value is None or value == "":
            return None
        if isinstance(value, BillStatus):
            return value
        try:
            return BillStatus(value)
        except ValueError:
            raise MTBillFilterInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(BillStatus.values())}."
            ) from None

    @field_validator("search", "number", "customer_id", mode="before")
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a text filter is absent or a usable fragment.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when empty.

        Raises:
            MTBillFilterInvalidFragment: If ``value`` is neither ``None`` nor a
                string.
        """
        return cls.validate_fragment(value)

    @field_validator("is_sent", mode="before")
    def validate_flags(cls, value: Union[bool, str, int, None]) -> Optional[bool]:
        """Validates that a three-state flag is absent or a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw flag value.

        Returns:
            Optional[bool]: The coerced flag, or ``None`` when not applied.

        Raises:
            MTBillFilterInvalidFlag: If ``value`` does not read as a boolean.
        """
        return cls.validate_flag(value)

    @field_validator("period_start", "period_end", mode="before")
    def validate_period_bound(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date, None]:
        """Validates that a period bound is absent or date-like.

        Args:
            value (Union[str, date, datetime, None]): Raw bound.

        Returns:
            Union[str, date, None]: The value handed back for Pydantic to parse,
            or ``None`` when not applied.

        Raises:
            MTBillFilterInvalidDate: If ``value`` is neither empty nor date-like.

        Notes:
            An empty string is "not applied", like every other cleared control
            on the filter bar. A date picker reset submits ``""``.
        """
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTBillFilterInvalidDate(
            f"Invalid period bound: {value!r}. Must be a date or an ISO string."
        )
