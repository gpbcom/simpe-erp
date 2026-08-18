from __future__ import annotations

# Standard library imports
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import BillingPeriodicity
from models.schemas.exceptions import (
    MTBillingPeriodicityRequestInvalidPeriodicity,
)


class BillingPeriodicityRequest(BaseModel):
    """The payload setting, or clearing, one customer's invoicing granularity.

    Attributes:
        periodicity (Optional[BillingPeriodicity]): The rule to bill this
            customer on, or ``None`` to put them back on the agency's own.

    Notes:
        - One field, like every other targeted update in this API. A route
          accepting a whole customer would let a stale payload clobber their
          address on the way past — the reason
          :class:`~models.schemas.requests.customers.status_update_request.StatusUpdateRequest`
          exists in the same shape.
        - **``null`` is a value here, not a missing one.** Sending it is how a
          manager takes an override off and puts the customer back on the
          agency's rule, so the field is optional in the schema and the absence
          of an override is representable. Without that, an override could be
          set and never removed except by editing the record by hand.
    """

    periodicity: Optional[BillingPeriodicity] = Field(
        default=None,
        description="The periodicity to bill this customer on. Null follows "
        "the agency's own.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("periodicity", mode="before")
    def validate_periodicity(
        cls, value: Union[str, BillingPeriodicity, None]
    ) -> Optional[BillingPeriodicity]:
        """Validates that ``periodicity``, when given, names a known rule.

        Args:
            value (Union[str, BillingPeriodicity, None]): Raw periodicity.

        Returns:
            Optional[BillingPeriodicity]: The coerced periodicity, or ``None``.

        Raises:
            MTBillingPeriodicityRequestInvalidPeriodicity: If ``value`` is
                neither ``None`` nor a known periodicity.
        """
        if value is None:
            return None
        if isinstance(value, BillingPeriodicity):
            return value
        try:
            return BillingPeriodicity(value)
        except ValueError:
            raise MTBillingPeriodicityRequestInvalidPeriodicity(
                f"Invalid periodicity: {value!r}. Must be one of: "
                f"{', '.join(BillingPeriodicity.values())}, or null to follow "
                f"the agency's own."
            ) from None

    ############################
    # Publicly Exposed Methods #
    ############################

    def follows_the_agency(self) -> bool:
        """Return whether this payload clears the customer's own rule.

        Returns:
            bool: ``True`` when no periodicity was named.

        Notes:
            Named rather than left as an ``is None`` check at the call site,
            because "clearing an override" and "a field nobody filled in" read
            identically in code and mean opposite things to whoever is logging
            what a manager just did.
        """
        return self.periodicity is None
