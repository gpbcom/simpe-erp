from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import List, Optional, Union

# Third-party imports
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    HttpUrl,
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
from models.people.hca import Hca
from models.schemas.exceptions import (
    MTHcaResponseInvalidContractType,
    MTHcaResponseInvalidDate,
    MTHcaResponseInvalidId,
    MTHcaResponseInvalidName,
)


class HcaResponse(BaseModel):
    """The shape a Home Care Assistant leaves the API in.

    Attributes:
        id (Optional[str]): Identifier, populated once the assistant is stored.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): Contact email address.
        address (PostalAddress): Home address, with its geocoding outcome.
        contract_type (ContractType): Employment contract.
        certifications (List[Certification]): Qualifications held.
        driving_license (Optional[DrivingLicense]): Driving licence, when held.
        photo_url (Optional[HttpUrl]): Portrait, when one is stored.
        availability (List[AvailabilitySlot]): Periods the assistant cannot
            work.
        created_at (Optional[datetime]): Creation timestamp.
        updated_at (Optional[datetime]): Last-update timestamp.

    Notes:
        - The nested value objects are the domain's own. They carry no secret
          and already validate themselves, so re-declaring them here would buy
          nothing but two definitions to keep in step.
        - The assistant is published in full because every field of it is
          something a manager may see. What this model buys is the *decision*:
          a field added to :class:`~models.people.hca.Hca` — a bank account, a
          note from a review — reaches the wire only if it is added here too.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated once the assistant is stored.",
    )
    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="Contact email address.")
    address: PostalAddress = Field(description="Home address.")
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
        description="Creation timestamp.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last-update timestamp.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTHcaResponseInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTHcaResponseInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("first_name", "last_name", mode="before")
    def validate_names(cls, value: Optional[str]) -> str:
        """Validates that a name is a non-empty string.

        Args:
            value (Optional[str]): Raw name value.

        Returns:
            str: The stripped name.

        Raises:
            MTHcaResponseInvalidName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaResponseInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("contract_type", mode="before")
    def validate_contract_type(
        cls, value: Union[str, ContractType, None]
    ) -> ContractType:
        """Validates that ``contract_type`` is a known contract.

        Args:
            value (Union[str, ContractType, None]): Raw ``contract_type``
                value.

        Returns:
            ContractType: The coerced contract type.

        Raises:
            MTHcaResponseInvalidContractType: If ``value`` is not a known
                contract type.
        """
        if isinstance(value, ContractType):
            return value
        try:
            return ContractType(value)
        except ValueError:
            raise MTHcaResponseInvalidContractType(
                f"Invalid contract_type: {value!r}. Must be one of: "
                f"{', '.join(ContractType.values())}."
            ) from None

    @field_validator("created_at", "updated_at", mode="before")
    def validate_timestamps(
        cls, value: Union[str, datetime, None]
    ) -> Optional[datetime]:
        """Validates that a timestamp is ``None``, a datetime or ISO-8601 text.

        Args:
            value (Union[str, datetime, None]): Raw timestamp value.

        Returns:
            Optional[datetime]: The parsed timestamp, or ``None``.

        Raises:
            MTHcaResponseInvalidDate: If ``value`` is neither ``None``, a
                datetime, nor a parseable ISO-8601 string.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise MTHcaResponseInvalidDate(
                f"Invalid timestamp: {value!r}. Must be a datetime, an "
                f"ISO-8601 string or None."
            )
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            raise MTHcaResponseInvalidDate(
                f"Invalid timestamp: {value!r}. Must be ISO-8601."
            ) from None

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
            Optional[str]: The URL as text, or ``None``.
        """
        return str(value) if value is not None else None

    @classmethod
    def from_hca(cls, hca: Hca) -> HcaResponse:
        """Build the response from a stored assistant.

        Args:
            hca (Hca): The assistant to publish.

        Returns:
            HcaResponse: The assistant, in its published shape.

        Raises:
            MTInvalidHcaResponseException: If a field of the assistant does not
                satisfy this model's validators.
        """
        return cls(
            id=hca.id,
            first_name=hca.first_name,
            last_name=hca.last_name,
            phone_number=str(hca.phone_number),
            email=str(hca.email),
            address=hca.address,
            contract_type=hca.contract_type,
            certifications=list(hca.certifications),
            driving_license=hca.driving_license,
            photo_url=hca.photo_url,
            availability=list(hca.availability),
            created_at=hca.created_at,
            updated_at=hca.updated_at,
        )
