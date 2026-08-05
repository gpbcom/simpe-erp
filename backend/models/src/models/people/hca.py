from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import ClassVar, Dict, List, Optional, Union

# Third-party imports
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    HttpUrl,
    JsonValue,
    field_serializer,
    field_validator,
)
from pydantic_extra_types.phone_numbers import PhoneNumber

# First-party imports
from models.enums import ContractType
from models.geo.postal_address import PostalAddress
from models.people.availability_slot import AvailabilitySlot
from models.people.certification import Certification
from models.people.driving_license import DrivingLicense
from models.people.exceptions import (
    MTHcaInvalidAddress,
    MTHcaInvalidAvailability,
    MTHcaInvalidCertifications,
    MTHcaInvalidContractType,
    MTHcaInvalidDate,
    MTHcaInvalidDrivingLicense,
    MTHcaInvalidEmail,
    MTHcaInvalidFirstName,
    MTHcaInvalidId,
    MTHcaInvalidLastName,
    MTHcaInvalidPhoneNumber,
    MTHcaInvalidPhotoUrl,
)


class Hca(BaseModel):
    """A Home Care Assistant: the person who travels to customers.

    Attributes:
        DEFAULT_PHONE_REGION (ClassVar[str]): Region assumed when a phone
            number is given in national rather than international form.
        PHOTO_KEY_PREFIX (ClassVar[str]): Object-store key prefix every
            photograph is written under. Mirrors
            :attr:`~models.configuration.s3_config.S3Config.DEFAULT_PHOTO_KEY_PREFIX`.
        id (Optional[str]): Identifier, populated on read from the store.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): Contact email address.
        address (PostalAddress): Home address, the start and end of each
            working day's route.
        company_id (Optional[str]): The company this assistant works for.
        contract_type (ContractType): Employment contract. Editable by a
            manager.
        certifications (List[Certification]): Qualifications held. Editable by
            a manager.
        driving_license (Optional[DrivingLicense]): Driving licence, when held.
        photo_url (Optional[HttpUrl]): URL of the portrait in the object
            store, when one has been uploaded.
        availability (List[AvailabilitySlot]): Periods the assistant cannot
            work. Declared by the assistant themselves.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
       - The home address is a routing depot, not just contact information: the
         planner charges the travel from home to the first intervention and back
         from the last, so an assistant living far from their customers is
         assigned differently from one living among them.
       - ``contract_type`` and ``certifications`` are the only two fields a
         manager may change. That restriction is enforced by the shape of the
         employment-update request model rather than by a check here — there is
         no manager-reachable route that accepts a whole assistant payload.
    """

    DEFAULT_PHONE_REGION: ClassVar[str] = "FR"
    PHOTO_KEY_PREFIX: ClassVar[str] = "hca-photos/"

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="Contact email address.")
    address: PostalAddress = Field(
        description="Home address, the start and end of each day's route.",
    )
    company_id: Optional[str] = Field(
        default=None, description="The company this assistant works for."
    )
    contract_type: ContractType = Field(description="Employment contract.")
    certifications: List[Certification] = Field(
        default_factory=list,
        description="Qualifications held.",
    )
    driving_license: Optional[DrivingLicense] = Field(
        default=None,
        description="Driving licence, when held.",
    )
    photo_url: Optional[HttpUrl] = Field(
        default=None,
        description="URL of the portrait in the object store.",
    )
    availability: List[AvailabilitySlot] = Field(
        default_factory=list,
        description="Periods the assistant cannot work.",
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
            MTHcaInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTHcaInvalidId(
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
            MTHcaInvalidFirstName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaInvalidFirstName(
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
            MTHcaInvalidLastName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaInvalidLastName(
                f"Invalid last_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("phone_number", mode="before")
    def validate_phone_number(cls, value: Optional[str]) -> str:
        """Validates that ``phone_number`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``phone_number`` value.

        Returns:
            str: The stripped number, handed on to the phone-number type.

        Raises:
            MTHcaInvalidPhoneNumber: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaInvalidPhoneNumber(
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
            MTHcaInvalidEmail: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaInvalidEmail(
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
            MTHcaInvalidAddress: If ``value`` is neither a
                :class:`~models.geo.postal_address.PostalAddress` nor a
                mapping.
        """
        if value is None or not isinstance(value, (PostalAddress, dict)):
            raise MTHcaInvalidAddress(
                f"Invalid address: {value!r}. Must be a PostalAddress or a mapping."
            )
        return value

    @field_validator("contract_type", mode="before")
    def validate_contract_type(
        cls, value: Union[str, ContractType, None]
    ) -> ContractType:
        """Validates that ``contract_type`` is a known contract type.

        Args:
            value (Union[str, ContractType, None]): Raw ``contract_type`` value.

        Returns:
            ContractType: The coerced contract type.

        Raises:
            MTHcaInvalidContractType: If ``value`` is not a known contract type.
        """
        if isinstance(value, ContractType):
            return value
        try:
            return ContractType(value)
        except ValueError:
            raise MTHcaInvalidContractType(
                f"Invalid contract_type: {value!r}. Must be one of: "
                f"{', '.join(ContractType.values())}."
            ) from None

    @field_validator("certifications", mode="before")
    def validate_certifications(cls, value: JsonValue) -> JsonValue:
        """Validates that ``certifications`` is a list of qualifications.

        Args:
            value (JsonValue): Raw list of certification payloads. ``None``
                yields an empty list.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTHcaInvalidCertifications: If ``value`` is neither ``None`` nor a
                list, or if an entry is neither a mapping nor a built
                certification.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTHcaInvalidCertifications(
                f"Invalid certifications: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (Certification, dict)):
                raise MTHcaInvalidCertifications(
                    f"Invalid certifications entry: {entry!r}. "
                    f"Must be a Certification or a mapping."
                )
        return value

    @field_validator("driving_license", mode="before")
    def validate_driving_license(
        cls, value: Union[DrivingLicense, Dict[str, JsonValue], None]
    ) -> Union[DrivingLicense, Dict[str, JsonValue], None]:
        """Validates that ``driving_license`` is a licence, a mapping or ``None``.

        Args:
            value (Union[DrivingLicense, Dict[str, JsonValue], None]): Raw
                ``driving_license`` value.

        Returns:
            Union[DrivingLicense, Dict[str, JsonValue], None]: The value handed
            back for Pydantic to build.

        Raises:
            MTHcaInvalidDrivingLicense: If ``value`` is neither ``None``, a
                :class:`~models.people.driving_license.DrivingLicense`, nor a
                mapping.
        """
        if value is None:
            return None
        if not isinstance(value, (DrivingLicense, dict)):
            raise MTHcaInvalidDrivingLicense(
                f"Invalid driving_license: {value!r}. "
                f"Must be a DrivingLicense, a mapping, or None."
            )
        return value

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Union[str, None]) -> Optional[str]:
        """Validates that ``company_id``, when given, is a non-empty string.

        Args:
            value (Union[str, None]): Raw ``company_id`` value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTHcaInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.

        Notes:
            Optional, because the assistants created before companies existed
            have none. A new one gets it from the application they came in on,
            or from the administrator who created them.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTHcaInvalidId(
                f"Invalid company_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("photo_url", mode="before")
    def validate_photo_url(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``photo_url`` points at a stored photograph.

        Args:
            value (Optional[str]): Raw ``photo_url`` value.

        Returns:
            Optional[str]: The stripped URL, or ``None``.

        Raises:
            MTHcaInvalidPhotoUrl: If ``value`` is neither ``None`` nor an
                ``http``/``https`` URL whose path lies under
                :attr:`PHOTO_KEY_PREFIX`.

        Notes:
            The portrait is optional by requirement, so a blank string reads as
            "no photo" rather than being rejected — an empty form field must
            not block saving an assistant.

            A non-empty value must be a URL the object store issued.
            Photographs are uploaded through the API and written to the bucket
            under a fixed key prefix, so requiring that prefix is what stops an
            arbitrary third-party URL being stored here: the application would
            otherwise render a remote image it does not control, and disclose
            every viewer's address to whoever hosts it.

            Which *bucket* the URL belongs to cannot be checked here, since the
            model has no access to configuration. The object store re-checks
            that before deleting, where getting it wrong would remove somebody
            else's object.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTHcaInvalidPhotoUrl(
                f"Invalid photo_url: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        if not stripped:
            return None
        if not stripped.startswith(("http://", "https://")):
            raise MTHcaInvalidPhotoUrl(
                f"Invalid photo_url: {stripped!r}. Must be an http or https URL."
            )
        if f"/{cls.PHOTO_KEY_PREFIX}" not in stripped:
            raise MTHcaInvalidPhotoUrl(
                f"Invalid photo_url: {stripped!r}. Must point at a photograph "
                f"stored by this application, under the "
                f"{cls.PHOTO_KEY_PREFIX!r} prefix."
            )
        return stripped

    @field_validator("availability", mode="before")
    def validate_availability(cls, value: JsonValue) -> JsonValue:
        """Validates that ``availability`` is a list of unavailability slots.

        Args:
            value (JsonValue): Raw list of slot payloads. ``None`` yields an
                empty list.

        Returns:
            JsonValue: The list handed back for Pydantic to build.

        Raises:
            MTHcaInvalidAvailability: If ``value`` is neither ``None`` nor a
                list, or if an entry is neither a mapping nor a built slot.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTHcaInvalidAvailability(
                f"Invalid availability: {value!r}. Must be a list or None."
            )
        for entry in value:
            if not isinstance(entry, (AvailabilitySlot, dict)):
                raise MTHcaInvalidAvailability(
                    f"Invalid availability entry: {entry!r}. "
                    f"Must be an AvailabilitySlot or a mapping."
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
            MTHcaInvalidDate: If ``value`` is neither ``None`` nor a
                datetime-like value.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise MTHcaInvalidDate(
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

    @field_serializer("photo_url")
    def serialize_photo_url(self, value: Optional[HttpUrl]) -> Optional[str]:
        """Serialize the portrait URL to a plain string.

        Args:
            value (Optional[HttpUrl]): The URL to serialize.

        Returns:
            Optional[str]: The URL as a string, or ``None``.
        """
        return str(value) if value is not None else None

    def full_name(self) -> str:
        """Return the assistant's display name.

        Returns:
            str: ``"<first_name> <last_name>"``.

        Notes:
            This is the name an intervention carries, so a planning reads as a
            person's diary rather than as a list of identifiers.
        """
        return f"{self.first_name} {self.last_name}"

    def can_drive(self) -> bool:
        """Return whether the assistant may be routed at driving speed.

        Returns:
            bool: ``True`` when a licence is held that permits driving a car.

        Notes:
            Used by the planner to pick which travel-time matrix applies. An
            assistant with no licence, or with a motorcycle-only licence, is
            routed at the slower transit speed.
        """
        if self.driving_license is None:
            return False
        return self.driving_license.can_drive_a_car()

    def is_available_on(self, day: date) -> bool:
        """Return whether the assistant can take work on a given day.

        Args:
            day (date): The day to test.

        Returns:
            bool: ``False`` when a whole-day unavailability slot covers the
            day, ``True`` otherwise.

        Notes:
            A partial-day slot leaves the day workable — it only carves a
            window out of it, which the solver models as a blocking interval
            rather than as an absence.
        """
        return not any(
            slot.covers(day) and slot.is_whole_day() for slot in self.availability
        )

    def blocking_slots_on(self, day: date) -> List[AvailabilitySlot]:
        """Return the partial-day slots that block part of a given day.

        Args:
            day (date): The day to inspect.

        Returns:
            List[AvailabilitySlot]: The slots covering ``day`` that block only
            a window of it.

        Notes:
            The solver turns each of these into a fixed interval that no
            intervention may overlap.
        """
        return [
            slot
            for slot in self.availability
            if slot.covers(day) and not slot.is_whole_day()
        ]
