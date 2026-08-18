from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTBillGenerationRequestInvalidCustomers,
    MTBillGenerationRequestInvalidDate,
)


class BillGenerationRequest(BaseModel):
    """The payload asking for a period to be billed.

    Attributes:
        reference_date (date): Any day inside the period to bill.
        customer_ids (Optional[List[str]]): Bill only these customers.

    Notes:
        - **A day, not a window.** The period is resolved from the agency's own
          periodicity, so a caller cannot ask for a fortnight the settings do not
          describe and produce an invoice whose window nobody could reproduce.
          Sending the day also means the same request means different things
          under different settings, which is the intent: "bill the month
          containing this day".
        - ``customer_ids`` is for re-running one customer whose first attempt
          failed. Omitted, every customer with billable work is billed. An
          **empty list** is refused rather than read as "everybody", because the
          two readings differ by a whole month's invoicing.
    """

    reference_date: date = Field(
        description="Any day inside the period to bill.",
    )
    customer_ids: Optional[List[str]] = Field(
        default=None,
        description="Bill only these customers, or all of them when omitted.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("reference_date", mode="before")
    def validate_reference_date(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date]:
        """Validates that ``reference_date`` is a date or an ISO string.

        Args:
            value (Union[str, date, datetime, None]): Raw date value.

        Returns:
            Union[str, date]: The value handed back for Pydantic to parse.

        Raises:
            MTBillGenerationRequestInvalidDate: If ``value`` is missing or is
                not date-like.
        """
        if value is None:
            raise MTBillGenerationRequestInvalidDate(
                "Invalid reference_date: a day inside the period is required."
            )
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTBillGenerationRequestInvalidDate(
            f"Invalid reference_date: {value!r}. Must be a date or an ISO string."
        )

    @field_validator("customer_ids", mode="before")
    def validate_customer_ids(cls, value: JsonValue) -> Optional[List[str]]:
        """Validates the customer restriction.

        Args:
            value (JsonValue): Raw ``customer_ids`` value.

        Returns:
            Optional[List[str]]: The stripped identifiers, de-duplicated, or
            ``None`` when every customer is to be billed.

        Raises:
            MTBillGenerationRequestInvalidCustomers: If ``value`` is neither
                ``None`` nor a non-empty list of non-empty strings.

        Notes:
            An empty list is refused rather than normalised to ``None``. "Bill
            nobody" and "bill everybody" are a month of invoicing apart, and a
            caller that meant the second omits the field.
        """
        if value is None:
            return None
        if not isinstance(value, list) or not value:
            raise MTBillGenerationRequestInvalidCustomers(
                f"Invalid customer_ids: {value!r}. Must be a non-empty list of "
                f"customer identifiers, or omitted to bill everybody."
            )
        identifiers: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTBillGenerationRequestInvalidCustomers(
                    f"Invalid customer identifier: {entry!r}. Must be a "
                    f"non-empty string."
                )
            stripped = entry.strip()
            if stripped not in identifiers:
                identifiers.append(stripped)
        return identifiers

    ############################
    # Publicly Exposed Methods #
    ############################

    def covers(self, customer_id: str) -> bool:
        """Return whether this request asks for a given customer to be billed.

        Args:
            customer_id (str): The customer being considered.

        Returns:
            bool: ``True`` when the request names no customers at all, or names
            this one.

        Notes:
            Resolving "omitted means everybody" here rather than at each call
            site is what stops a run that meant to bill one customer quietly
            billing the agency's whole book.
        """
        return self.customer_ids is None or customer_id in self.customer_ids
