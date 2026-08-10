from __future__ import annotations

# Standard library imports
from typing import ClassVar, Type, Union

# Third-party imports
from pydantic import Field, field_validator

from models.base.exceptions import MTInvalidPersonException
from models.base.person import Person

# First-party imports
from models.enums import RegistrationStatus
from models.geo.postal_address import PostalAddress
from models.people.customer.exceptions import (
    MTCustomerInvalidAddress,
    MTCustomerInvalidDate,
    MTCustomerInvalidEmail,
    MTCustomerInvalidFirstName,
    MTCustomerInvalidId,
    MTCustomerInvalidLastName,
    MTCustomerInvalidPhoneNumber,
    MTCustomerInvalidRegistrationStatus,
)


class Customer(Person):
    """A person receiving home care, and the party a quote is addressed to.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
            Inherited from :class:`~models.people.person.Person`.
        first_name (str): Given name. Inherited.
        last_name (str): Family name. Inherited.
        phone_number (PhoneNumber): Contact telephone number. Inherited.
        email (EmailStr): Contact email address. Inherited.
        address (PostalAddress): Where the care is delivered. Inherited, and
            re-declared only to say so.
        registration_status (RegistrationStatus): Whether the customer is
            served, in discussion, or stopped. **Defaults to
            :attr:`~models.enums.RegistrationStatus.PROSPECT`.**
        created_at (Optional[datetime]): Creation timestamp, set by the store.
            Inherited.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store. Inherited.

    Notes:
        - **Almost all of it comes from
          :class:`~models.people.person.Person`.** A customer is a person and
          one flag: everything else — the names, the address, the contact
          details, their validators and
          :meth:`~models.people.person.Person.full_name` — is the same record
          an assistant keeps, and was a second copy of it until the base
          existed. The ``INVALID_*`` class attributes are how the inherited
          rules go on raising this model's own exceptions.
        - A customer carries **no ``company_id``**, unlike an assistant and an
          application. That is a real gap rather than an oversight of this
          refactor — customers are global, which is why a company is not yet a
          tenancy boundary — and it is why the field sits on the two subclasses
          that have it rather than on the base.
        - The address is where interventions actually take place, so it is the
          coordinate the planner routes to. A customer whose address never
          geocodes cannot be scheduled; that surfaces as an unassigned
          requirement rather than as a validation error here, because a quote
          must still be printable for an address the geocoder does not know.
    """

    INVALID_ID: ClassVar[Type[MTInvalidPersonException]] = MTCustomerInvalidId
    INVALID_FIRST_NAME: ClassVar[Type[MTInvalidPersonException]] = (
        MTCustomerInvalidFirstName
    )
    INVALID_LAST_NAME: ClassVar[Type[MTInvalidPersonException]] = (
        MTCustomerInvalidLastName
    )
    INVALID_PHONE_NUMBER: ClassVar[Type[MTInvalidPersonException]] = (
        MTCustomerInvalidPhoneNumber
    )
    INVALID_EMAIL: ClassVar[Type[MTInvalidPersonException]] = MTCustomerInvalidEmail  # noqa: E501
    INVALID_ADDRESS: ClassVar[Type[MTInvalidPersonException]] = MTCustomerInvalidAddress  # noqa: E501
    INVALID_DATE: ClassVar[Type[MTInvalidPersonException]] = MTCustomerInvalidDate  # noqa: E501

    address: PostalAddress = Field(description="Where the care is delivered.")
    registration_status: RegistrationStatus = Field(
        default=RegistrationStatus.PROSPECT,
        description="Whether the customer is served, "  # noqa: E501
        "in discussion, or stopped.",
    )

    @field_validator("registration_status", mode="before")
    def validate_registration_status(
        cls, value: Optional[str, RegistrationStatus]
    ) -> RegistrationStatus:
        """Validates that ``registration_status`` is a known status.

        Args:
            value (Optional[str, RegistrationStatus]): Raw status value.
                ``None`` falls back to :attr:`RegistrationStatus.PROSPECT`.

        Returns:
            RegistrationStatus: The coerced status.

        Raises:
            MTCustomerInvalidRegistrationStatus: If ``value`` is not a known
                registration status.

        Notes:
            The ``None`` fallback tracks the field default deliberately. A
            payload that omits the status and one that sends ``null`` mean the
            same thing — "nobody has said" — and the safe reading of that is
            *prospect*, because it is the state that schedules nothing.
        """
        if value is None:
            return RegistrationStatus.PROSPECT
        if isinstance(value, RegistrationStatus):
            return value
        try:
            return RegistrationStatus(value)
        except ValueError:
            raise MTCustomerInvalidRegistrationStatus(
                f"Invalid registration_status: {value!r}. Must be one of: "
                f"{', '.join(RegistrationStatus.values())}."
            ) from None

    def is_active(self) -> bool:
        """Return whether the customer is on the books as a served customer.

        Returns:
            bool: ``True`` when the registration status is active.

        Notes:
            - **This says what state they are in, and nothing more.** It used to
              claim the customer "may be quoted and scheduled", which was safe
              while there were two states and became wrong with three: a prospect
              is not active and yet quoting them is the entire point of the
              state. Ask :meth:`can_be_scheduled` about the planner, and nothing
              about quoting — no code enforces that today.
            - A stopped customer keeps their history — past quotes and delivered
              interventions stay readable — but takes no new work.
        """
        return self.registration_status is RegistrationStatus.ACTIVE

    def can_be_scheduled(self) -> bool:
        """Return whether the planner may place visits for this customer.

        Returns:
            bool: ``True`` only for an active customer.

        Notes:
            Delegates to
            :meth:`~models.enums.RegistrationStatus.can_be_scheduled`, where
            the rule lives. It is restated here because the requirement builder
            holds a ``Customer`` rather than a status, and
            ``customer.can_be_scheduled()`` is the sentence that reads correctly
            at the one call site that matters.
        """
        return self.registration_status.can_be_scheduled()
