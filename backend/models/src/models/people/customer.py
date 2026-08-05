from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Dict, Optional, Union

# Third-party imports
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
)
from pydantic_extra_types.phone_numbers import PhoneNumber

# First-party imports
from models.enums import RegistrationStatus
from models.geo.postal_address import PostalAddress
from models.people.exceptions import (
    MTCustomerInvalidAddress,
    MTCustomerInvalidDate,
    MTCustomerInvalidEmail,
    MTCustomerInvalidFirstName,
    MTCustomerInvalidId,
    MTCustomerInvalidLastName,
    MTCustomerInvalidPhoneNumber,
    MTCustomerInvalidRegistrationStatus,
)


class Customer(BaseModel):
    """A person receiving home care, and the party a quote is addressed to.

    Attributes:
        DEFAULT_PHONE_REGION (ClassVar[str]): Region assumed when a phone
            number is given in national rather than international form.
        id (Optional[str]): Identifier, populated on read from the store.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): Contact email address.
        address (PostalAddress): Where the care is delivered.
        registration_status (RegistrationStatus): Whether the customer is
            currently served.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        The address is where interventions actually take place, so it is the
        coordinate the planner routes to. A customer whose address never
        geocodes cannot be scheduled; that surfaces as an unassigned
        requirement rather than as a validation error here, because a quote
        must still be printable for an address the geocoder does not know.
    """

    DEFAULT_PHONE_REGION: ClassVar[str] = "FR"

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="Contact email address.")
    address: PostalAddress = Field(description="Where the care is delivered.")
    registration_status: RegistrationStatus = Field(
        default=RegistrationStatus.ACTIVE,
        description="Whether the customer is currently served.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="Creation timestamp, set by the store.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last-update timestamp, set by the store.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is persisted.

        Raises:
            MTCustomerInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("first_name", mode="before")
    def validate_first_name(cls, value: Optional[str]) -> str:
        """Validates that ``first_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``first_name`` value.

        Returns:
            str: The stripped given name.

        Raises:
            MTCustomerInvalidFirstName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerInvalidFirstName(
                f"Invalid first_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("last_name", mode="before")
    def validate_last_name(cls, value: Optional[str]) -> str:
        """Validates that ``last_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``last_name`` value.

        Returns:
            str: The stripped family name.

        Raises:
            MTCustomerInvalidLastName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerInvalidLastName(
                f"Invalid last_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("phone_number", mode="before")
    def validate_phone_number(cls, value: Optional[str]) -> str:
        """Validates that ``phone_number`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``phone_number`` value.

        Returns:
            str: The stripped number, handed on to the phone-number type for
            parsing.

        Raises:
            MTCustomerInvalidPhoneNumber: If ``value`` is not a non-empty
                string.

        Notes:
            Only the shape is checked here. Whether the digits form a dialable
            number is decided by
            :class:`~pydantic_extra_types.phone_numbers.PhoneNumber`, which
            wraps the ``phonenumbers`` library; this validator exists so a
            missing or non-string value raises the model's own exception rather
            than a bare ``ValidationError``.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerInvalidPhoneNumber(
                f"Invalid phone_number: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("email", mode="before")
    def validate_email(cls, value: Optional[str]) -> str:
        """Validates that ``email`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``email`` value.

        Returns:
            str: The stripped address, handed on to ``EmailStr`` for parsing.

        Raises:
            MTCustomerInvalidEmail: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCustomerInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("address", mode="before")
    def validate_address(
        cls, value: Union[PostalAddress, Dict[str, JsonValue], None]
    ) -> Union[PostalAddress, Dict[str, JsonValue]]:
        """Validates that ``address`` is an address or a mapping.

        Args:
            value (Union[PostalAddress, Dict[str, JsonValue], None]): Raw
                ``address`` value.

        Returns:
            Union[PostalAddress, Dict[str, JsonValue]]: The value handed back
            for Pydantic to build.

        Raises:
            MTCustomerInvalidAddress: If ``value`` is neither a
                :class:`~models.geo.postal_address.PostalAddress` nor a
                mapping.

        Notes:
            The payload is not coerced here, so a malformed address raises its
            own field-level exception naming the offending part rather than a
            generic "invalid address".
        """
        if value is None or not isinstance(value, (PostalAddress, dict)):
            raise MTCustomerInvalidAddress(
                f"Invalid address: {value!r}. Must be a PostalAddress or a mapping."
            )
        return value

    @field_validator("registration_status", mode="before")
    def validate_registration_status(
        cls, value: Union[str, RegistrationStatus, None]
    ) -> RegistrationStatus:
        """Validates that ``registration_status`` is a known status.

        Args:
            value (Union[str, RegistrationStatus, None]): Raw status value.
                ``None`` falls back to :attr:`RegistrationStatus.ACTIVE`.

        Returns:
            RegistrationStatus: The coerced status.

        Raises:
            MTCustomerInvalidRegistrationStatus: If ``value`` is not a known
                registration status.
        """
        if value is None:
            return RegistrationStatus.ACTIVE
        if isinstance(value, RegistrationStatus):
            return value
        try:
            return RegistrationStatus(value)
        except ValueError:
            raise MTCustomerInvalidRegistrationStatus(
                f"Invalid registration_status: {value!r}. Must be one of: "
                f"{', '.join(RegistrationStatus.values())}."
            ) from None

    @field_validator("created_at", "updated_at", mode="before")
    def validate_date(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a timestamp is a datetime, an ISO string or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp value.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic to
            parse.

        Raises:
            MTCustomerInvalidDate: If ``value`` is neither ``None`` nor a
                datetime-like value.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise MTCustomerInvalidDate(
            f"Invalid timestamp: {value!r}. "
            f"Must be a datetime, an ISO-8601 string, or None."
        )

    @field_serializer("created_at", "updated_at")
    def serialize_date(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    def full_name(self) -> str:
        """Return the customer's display name.

        Returns:
            str: ``"<first_name> <last_name>"``.
        """
        return f"{self.first_name} {self.last_name}"

    def is_active(self) -> bool:
        """Return whether the customer may be quoted and scheduled.

        Returns:
            bool: ``True`` when the registration status is active.

        Notes:
            A stopped customer keeps their history — past quotes and delivered
            interventions stay readable — but takes no new work.
        """
        return self.registration_status is RegistrationStatus.ACTIVE
