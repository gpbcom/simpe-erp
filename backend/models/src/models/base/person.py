from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Dict, Optional, Type, Union

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
from models.geo.postal_address import PostalAddress
from models.base.exceptions.person_exceptions import (
    MTInvalidPersonException,
    MTPersonInvalidAddress,
    MTPersonInvalidDate,
    MTPersonInvalidEmail,
    MTPersonInvalidFirstName,
    MTPersonInvalidId,
    MTPersonInvalidLastName,
    MTPersonInvalidPhoneNumber,
)


class Person(BaseModel):
    """What every human record in the system carries, and nothing more.

    Attributes:
        DEFAULT_PHONE_REGION (ClassVar[str]): Region assumed when a phone
            number is given in national rather than international form.
        INVALID_ID (ClassVar[Type[MTInvalidPersonException]]): Exception a
            subclass raises for a malformed identifier.
        INVALID_FIRST_NAME (ClassVar[Type[MTInvalidPersonException]]): Same,
            for the given name.
        INVALID_LAST_NAME (ClassVar[Type[MTInvalidPersonException]]): Same,
            for the family name.
        INVALID_PHONE_NUMBER (ClassVar[Type[MTInvalidPersonException]]): Same,
            for the telephone number.
        INVALID_EMAIL (ClassVar[Type[MTInvalidPersonException]]): Same, for the
            email address.
        INVALID_ADDRESS (ClassVar[Type[MTInvalidPersonException]]): Same, for
            the postal address.
        INVALID_DATE (ClassVar[Type[MTInvalidPersonException]]): Same, for a
            timestamp.
        id (Optional[str]): Identifier, populated on read from the store.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): Contact email address.
        address (PostalAddress): Where the person is reached.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - **A base, not an entity.** Nothing stores a ``Person``. It exists so
          :class:`~models.people.hca.Hca`,
          :class:`~models.people.customer.Customer` and
          :class:`~models.people.hca_application.HcaApplication` state the same
          eight fields and their seven validators once instead of three times.
          Those three had drifted already — the same rule was spelled three
          ways, and a fix to one of them was a fix to one of them.
        - **It is deliberately not an account.**
          :class:`~models.auth.user.User` does not descend from this and must
          not: an account carries a password hash, a role and an active flag,
          and a customer that inherited those would publish a credential field
          on every response and a role nobody granted. A person is somebody the
          agency deals with. An account is something that signs in. Some people
          have one, most do not, and the two are joined by ``hca_id`` rather
          than by inheritance.
        - **Per-model exceptions survive.** A validator here raises
          ``cls.INVALID_*``, and Pydantic binds ``cls`` to the concrete
          subclass — so an ``Hca`` still raises ``MTHcaInvalidEmail`` and a
          ``Customer`` still raises ``MTCustomerInvalidEmail``. That matters
          beyond tidiness: the API's exception-to-status map is keyed on those
          classes, and collapsing them into one would answer every malformed
          field with the same status for every model.
        - The defaults below are the generic ``MTPerson*`` classes, so a
          subclass that forgets to declare one still raises something typed
          rather than a bare ``ValueError``.
    """

    DEFAULT_PHONE_REGION: ClassVar[str] = "FR"

    INVALID_ID: ClassVar[Type[MTInvalidPersonException]] = MTPersonInvalidId
    INVALID_FIRST_NAME: ClassVar[Type[MTInvalidPersonException]] = (
        MTPersonInvalidFirstName
    )
    INVALID_LAST_NAME: ClassVar[Type[MTInvalidPersonException]] = (
        MTPersonInvalidLastName
    )
    INVALID_PHONE_NUMBER: ClassVar[Type[MTInvalidPersonException]] = (
        MTPersonInvalidPhoneNumber
    )
    INVALID_EMAIL: ClassVar[Type[MTInvalidPersonException]] = MTPersonInvalidEmail  # noqa: E501
    INVALID_ADDRESS: ClassVar[Type[MTInvalidPersonException]] = MTPersonInvalidAddress  # noqa: E501
    INVALID_DATE: ClassVar[Type[MTInvalidPersonException]] = MTPersonInvalidDate  # noqa: E501

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="Contact email address.")
    address: PostalAddress = Field(description="Where the person is reached.")
    created_at: Optional[datetime] = Field(
        default=None,
        description="Creation timestamp, set by the store.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last-update timestamp, set by the store.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is persisted.

        Raises:
            MTInvalidPersonException: The subclass's :attr:`INVALID_ID`, if
                ``value`` is neither ``None`` nor a non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_ID(
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
            MTInvalidPersonException: The subclass's
                :attr:`INVALID_FIRST_NAME`, if ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_FIRST_NAME(
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
            MTInvalidPersonException: The subclass's :attr:`INVALID_LAST_NAME`,
                if ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_LAST_NAME(
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
            MTInvalidPersonException: The subclass's
                :attr:`INVALID_PHONE_NUMBER`, if ``value`` is not a non-empty
                string.

        Notes:
            Only the shape is checked here. Whether the digits form a dialable
            number is decided by
            :class:`~pydantic_extra_types.phone_numbers.PhoneNumber`, which
            wraps the ``phonenumbers`` library. This validator exists so a
            missing or non-string value raises the model's own exception rather
            than a bare ``ValidationError``.
        """
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_PHONE_NUMBER(
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
            MTInvalidPersonException: The subclass's :attr:`INVALID_EMAIL`, if
                ``value`` is not a non-empty string.

        Notes:
            The address is **not** lower-cased here. For most people it is
            contact information, and rewriting what somebody typed is not this
            model's business. A subclass whose address becomes a *sign-in*
            overrides this and lower-cases it, because sign-in is
            case-insensitive and the uniqueness index must not be defeatable by
            capitalisation — see
            :meth:`~models.people.hca_application.HcaApplication.validate_email`.
        """
        if not isinstance(value, str) or not value.strip():
            raise cls.INVALID_EMAIL(
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
            MTInvalidPersonException: The subclass's :attr:`INVALID_ADDRESS`,
                if ``value`` is neither a
                :class:`~models.geo.postal_address.PostalAddress` nor a
                mapping.

        Notes:
            The payload is not coerced here, so a malformed address raises its
            own field-level exception naming the offending part rather than a
            generic "invalid address".
        """
        if value is None or not isinstance(value, (PostalAddress, dict)):
            raise cls.INVALID_ADDRESS(
                f"Invalid address: {value!r}. "  # noqa: E501
                "Must be a PostalAddress or a mapping."
            )
        return value

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
            MTInvalidPersonException: The subclass's :attr:`INVALID_DATE`, if
                ``value`` is neither ``None`` nor a datetime-like value.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise cls.INVALID_DATE(
            f"Invalid timestamp: {value!r}. "
            f"Must be a datetime, an ISO-8601 string, or None."
        )

    ###############################
    # Fields Serialization Method #
    ###############################

    @field_serializer("created_at", "updated_at")
    def serialize_date(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def full_name(self) -> str:
        """Return the person's display name.

        Returns:
            str: ``"<first_name> <last_name>"``.

        Notes:
            A method rather than a stored field, so it cannot disagree with the
            two names it is built from. That is also why
            :class:`~models.auth.user.User` cannot descend from this class: an
            account stores a display name of its own, chosen by its holder, and
            a field and a method of the same name cannot coexist.
        """
        return f"{self.first_name} {self.last_name}"
