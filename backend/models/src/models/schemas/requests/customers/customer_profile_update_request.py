from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

# First-party imports
from models.geo.postal_address import PostalAddress
from models.schemas.exceptions import MTCustomerProfileUpdateRequestInvalidName


class CustomerProfileUpdateRequest(BaseModel):
    """The fields a household may change about themselves.

    Attributes:
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): Contact email address.
        address (PostalAddress): Where the care is delivered.

    Notes:
        - **What is absent is the point**, exactly as on
          :class:`~models.schemas.requests.hca.hca_profile_update_request.HcaProfileUpdateRequest`.
          Two fields are deliberately missing and each would be a hole:

          - ``registration_status``. A household that could set their own status
            would promote themselves from ``prospect`` to ``active`` — and being
            active is precisely what makes the planner schedule their work. That
            is the whole gate ``can_be_scheduled`` exists for, handed to the
            party it is meant to gate.
          - ``billing_periodicity``. How often somebody is invoiced is a
            commercial term the agency agrees, not a preference. A manager sets
            it through ``PATCH /api/v1/customers/{id}/billing-periodicity``.

          Leaving them out means they cannot be smuggled in, rather than relying
          on an endpoint remembering to ignore them.
        - **The address is editable, and it is not a cosmetic field.** It is
          where care is delivered and what every planning run routes to, so a
          household correcting it is the fastest path to work being planned to
          the right door — and re-geocoding is what the model does on the way
          in, so a street the map cannot find is stored with the failure
          recorded rather than refused.
        - Every field is required. This replaces the contact block wholesale, so
          a payload omitting the telephone number would be a household clearing
          it — which is how somebody becomes unreachable when an assistant is
          running late.
    """

    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="Contact email address.")
    address: PostalAddress = Field(description="Where the care is delivered.")

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("first_name", "last_name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that a name part is a non-empty string.

        Args:
            value (Optional[str]): Raw name value.

        Returns:
            str: The trimmed name.

        Raises:
            MTCustomerProfileUpdateRequestInvalidName: If ``value`` is not a
                non-empty string.

        Notes:
            Both parts are required here, unlike on an *account*, where a
            mononym or a service account may leave the given name blank. This
            is a household on a printed invoice and on an assistant's round
            sheet, and half a name on either is a call to the office.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerProfileUpdateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()
