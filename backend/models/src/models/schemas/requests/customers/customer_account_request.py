from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

# First-party imports
from models.schemas.exceptions import MTCustomerAccountRequestInvalidFullName


class CustomerAccountRequest(BaseModel):
    """The payload a manager sends to give a customer access to their space.

    Attributes:
        email (EmailStr): The sign-in address.
        full_name (str): The display name.

    Notes:
        - **The household is not in the payload; it is in the path.** The route
          is ``POST /customers/{customer_id}/account``, and taking the
          identifier from the body as well would give a well-formed request two
          answers to "whose account is this" — the shape a mistyped invitation
          takes when it lands on somebody else's file.
        - **There is no password field**, exactly as on
          :class:`~models.schemas.requests.account.staff_account_request.StaffAccountRequest`.
          The temporary password is generated server-side and returned once;
          letting a manager choose it means the first credential is one they
          typed into a ticket and probably reused.
        - **There is no role either**, and here it matters more than it does for
          staff. This route mints a *customer*, which is the one role that is
          not on the staff ladder; a role field would be a way to ask for an
          employee account through a customer-facing endpoint.
        - The address is not defaulted from the customer record. A household's
          postal address is where care is delivered, and the person who reads
          the agency's email is often a son or a daughter at another one.
    """

    email: EmailStr = Field(description="The sign-in address.")
    full_name: str = Field(description="The display name.")

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("full_name", mode="before")
    def validate_full_name(cls, value: Optional[str]) -> str:
        """Validates that the display name is a non-empty string.

        Args:
            value (Optional[str]): Raw ``full_name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTCustomerAccountRequestInvalidFullName: If ``value`` is not a
                non-empty string.

        Notes:
            Trimmed rather than taken literally. The name is what the portal
            greets somebody by and what the account list shows a manager, and a
            leading space sorts it above every other row.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerAccountRequestInvalidFullName(
                f"Invalid full_name: {value!r}. An account must carry a display name."
            )
        return value.strip()
