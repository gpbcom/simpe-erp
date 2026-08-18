from __future__ import annotations

# Standard library imports
from typing import Dict, Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, JsonValue, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

# First-party imports
from models.geo.postal_address import PostalAddress
from models.people.hca.driving_license import DrivingLicense
from models.schemas.exceptions import (
    MTHcaProfileUpdateRequestInvalidAddress,
    MTHcaProfileUpdateRequestInvalidName,
)


class HcaProfileUpdateRequest(BaseModel):
    """The fields an assistant may change about themselves.

    Attributes:
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): Contact email address.
        address (PostalAddress): Home address.
        driving_license (Optional[DrivingLicense]): Driving licence, when
            one is held.

    Notes:
        - **What is absent is the point.** There is no ``contract_type``, no
          ``certifications`` and no ``role``. An assistant does not decide what
          they are qualified to do, what they are employed as, or what they are
          allowed to do — a manager sets the first two through
          ``PATCH /api/v1/hcas/{id}/employment`` and an administrator the third
          through ``POST /api/v1/users/{id}/promote``. Leaving the fields out of
          the payload means they cannot be smuggled in, rather than relying on
          an endpoint remembering to ignore them. A manager editing their own
          record uses those two endpoints, exactly as they would for anybody
          else's — so this payload never needs to widen for them.
        - **The driving licence is here**, because it is the assistant's own
          document rather than a decision about them. It also decides which
          travel speed the planner routes them at, so an assistant who passes
          their test wants it recorded the same day.
        - There is no ``photo_url`` either. A photograph is uploaded as a file
          and its URL is minted by the object store. Accepting a URL here would
          let an assistant point their portrait at any address on the internet,
          which the manager's map would then load on every pin.
        - Changing the address re-geocodes it, because
          :class:`~models.geo.postal_address.PostalAddress` resolves during
          validation. That is wanted: an assistant who moves must be routed from
          their new home on the next planning run.
    """

    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="Contact email address.")
    address: PostalAddress = Field(description="Home address.")
    driving_license: Optional[DrivingLicense] = Field(
        default=None,
        description="Driving licence, when one is held.",
    )

    @field_validator("first_name", "last_name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that a name part is a non-empty string.

        Args:
            value (Optional[str]): Raw name value.

        Returns:
            str: The stripped name.

        Raises:
            MTHcaProfileUpdateRequestInvalidName: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaProfileUpdateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("address", mode="before")
    def validate_address(
        cls, value: Union[PostalAddress, Dict[str, JsonValue], None]
    ) -> Union[PostalAddress, Dict[str, JsonValue]]:
        """Validates that ``address`` is an address or a mapping.

        Args:
            value (Union[PostalAddress, Dict[str, JsonValue], None]): Raw
                address value.

        Returns:
            Union[PostalAddress, Dict[str, JsonValue]]: The value handed back
            for Pydantic to build.

        Raises:
            MTHcaProfileUpdateRequestInvalidAddress: If ``value`` is neither an
                address nor a mapping.
        """
        if value is None or not isinstance(value, (PostalAddress, dict)):
            raise MTHcaProfileUpdateRequestInvalidAddress(
                f"Invalid address: {value!r}. Must be an address or a mapping."
            )
        return value
