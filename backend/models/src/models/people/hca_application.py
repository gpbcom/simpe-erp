from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

# First-party imports
from models.enums import ContractType, HcaApplicationStatus
from models.geo.postal_address import PostalAddress
from models.people.exceptions import (
    MTHcaApplicationInvalidCompany,
    MTHcaApplicationInvalidDate,
    MTHcaApplicationInvalidDecision,
    MTHcaApplicationInvalidEmail,
    MTHcaApplicationInvalidId,
    MTHcaApplicationInvalidName,
    MTHcaApplicationInvalidPasswordHash,
    MTHcaApplicationInvalidStatus,
)


class HcaApplication(BaseModel):
    """An assistant's own request to work for a company, awaiting validation.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        company_id (str): The company they chose to apply to.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): The address that will become their sign-in.
        address (PostalAddress): Where they live; the start of every round.
        contract_type (Optional[ContractType]): The contract they are applying
            for, if the company asked.
        hashed_password (str): The credential they chose, already hashed.
        status (HcaApplicationStatus): Where the application has got to.
        decided_by (Optional[str]): The manager who approved or declined it.
        decided_at (Optional[datetime]): When that decision was made.
        rejection_reason (Optional[str]): Why it was declined.
        hca_id (Optional[str]): The assistant record created on approval.
        created_at (Optional[datetime]): When it was submitted.
        updated_at (Optional[datetime]): Last-update timestamp.

    Notes:
        - **No account exists while this is pending.** The applicant's chosen
          password is hashed and parked here, and only on approval does a
         :class:`~models.auth.user.User` get created from it. The alternative —
          creating an inactive account up front — puts an unvetted row in the
          table every guard reads from, and one forgotten ``is_active`` check
          would let a stranger in.
        - The password is stored **hashed**, never in plain text, even though
          nothing can sign in with it yet. An application that sits for a week
          waiting for a manager is a plaintext credential sitting for a week.
        - A decided application keeps its record rather than being deleted, so a
          second application from somebody previously declined is recognisable as
          one.
    """

    id: Optional[str] = Field(
        default=None, description="Identifier, assigned by the store."
    )
    company_id: str = Field(description="The company applied to.")
    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="The address that becomes the sign-in.")
    address: PostalAddress = Field(description="Where the applicant lives.")
    contract_type: Optional[ContractType] = Field(
        default=None, description="The contract applied for."
    )
    hashed_password: str = Field(description="The chosen credential, hashed.")
    status: HcaApplicationStatus = Field(
        default=HcaApplicationStatus.PENDING,
        description="Where the application has got to.",
    )
    decided_by: Optional[str] = Field(
        default=None, description="The manager who decided it."
    )
    decided_at: Optional[datetime] = Field(
        default=None, description="When it was decided."
    )
    rejection_reason: Optional[str] = Field(
        default=None, description="Why it was declined."
    )
    hca_id: Optional[str] = Field(
        default=None, description="The assistant record created on approval."
    )
    created_at: Optional[datetime] = Field(
        default=None, description="When it was submitted."
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last-update timestamp."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("id", "hca_id", "decided_by", mode="before")
    def validate_optional_identifiers(cls, value: Union[str, None]) -> Optional[str]:
        """Validates that an optional identifier is a non-empty string.

        Args:
            value (Union[str, None]): Raw identifier value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTHcaApplicationInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTHcaApplicationInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Union[str, None]) -> str:
        """Validates that a company was chosen.

        Args:
            value (Union[str, None]): Raw ``company_id`` value.

        Returns:
            str: The company identifier.

        Raises:
            MTHcaApplicationInvalidCompany: If ``value`` is not a non-empty
                string.

        Notes:
            Required, and there is no default. An application to nobody in
            particular has no one with standing to approve it, and would sit in
            the table for ever.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaApplicationInvalidCompany(
                f"Invalid company_id: {value!r}. An application must name the "
                f"company it is addressed to."
            )
        return value.strip()

    @field_validator("first_name", "last_name", mode="before")
    def validate_names(cls, value: Union[str, None]) -> str:
        """Validates that a name is a non-empty string.

        Args:
            value (Union[str, None]): Raw name value.

        Returns:
            str: The trimmed name.

        Raises:
            MTHcaApplicationInvalidName: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaApplicationInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("email", mode="before")
    def validate_email(cls, value: Union[str, None]) -> str:
        """Validates that the address is present, and lower-cases it.

        Args:
            value (Union[str, None]): Raw ``email`` value.

        Returns:
            str: The lower-cased address.

        Raises:
            MTHcaApplicationInvalidEmail: If ``value`` is not a non-empty
                string.

        Notes:
            Lower-cased because this address becomes the sign-in on approval,
            and an account stored with different capitalisation than the one
            typed at the login screen is an account nobody can reach.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaApplicationInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("hashed_password", mode="before")
    def validate_hashed_password(cls, value: Union[str, None]) -> str:
        """Validates that the stored credential is a hash.

        Args:
            value (Union[str, None]): Raw ``hashed_password`` value.

        Returns:
            str: The hash.

        Raises:
            MTHcaApplicationInvalidPasswordHash: If ``value`` is not a non-empty
                string.

        Notes:
            The value is never logged, echoed or compared here — only its
            presence is checked. What this field must never hold is a plain
            password, and the caller hashing before construction is what
            guarantees that; a validator cannot tell the two apart.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaApplicationInvalidPasswordHash(
                "Invalid hashed_password: a hashed credential is required."
            )
        return value

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Union[str, HcaApplicationStatus, None]
    ) -> HcaApplicationStatus:
        """Validates that ``status`` is a known status.

        Args:
            value (Union[str, HcaApplicationStatus, None]): Raw status value.

        Returns:
            HcaApplicationStatus: The coerced status.

        Raises:
            MTHcaApplicationInvalidStatus: If ``value`` is not a known status.
        """
        if value is None:
            return HcaApplicationStatus.PENDING
        if isinstance(value, HcaApplicationStatus):
            return value
        try:
            return HcaApplicationStatus(value)
        except ValueError:
            raise MTHcaApplicationInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(HcaApplicationStatus.values())}."
            ) from None

    @field_validator("created_at", "updated_at", "decided_at", mode="before")
    def validate_timestamps(
        cls, value: Union[datetime, str, None]
    ) -> Optional[datetime]:
        """Validates that a timestamp is a datetime.

        Args:
            value (Union[datetime, str, None]): Raw timestamp value.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTHcaApplicationInvalidDate: If ``value`` is neither ``None`` nor a
                datetime or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTHcaApplicationInvalidDate(
                    f"Invalid timestamp: {value!r}. Must be an ISO-8601 datetime."
                ) from None
        raise MTHcaApplicationInvalidDate(
            f"Invalid timestamp: {value!r}. Must be a datetime."
        )

    ############################
    # Model Validation Methods #
    ############################

    @model_validator(mode="after")
    def check_decision(self) -> HcaApplication:
        """Ensure a decided application records who decided it.

        Returns:
            HcaApplication: ``self`` for chaining.

        Raises:
            MTHcaApplicationInvalidDecision: If the status is terminal and no
                decider is recorded.

        Notes:
            Approving somebody into the workforce is an accountable act. An
            approved application with nobody's name against it is a hole in the
            audit trail exactly where it matters — and refusing to build one is
            the only way to keep it from being written.
        """
        if self.status.is_terminal() and not self.decided_by:
            raise MTHcaApplicationInvalidDecision(
                f"Invalid decided_by: an application that is "
                f"{self.status.value} must record who decided it."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def full_name(self) -> str:
        """Return the applicant's display name.

        Returns:
            str: Given name and family name.
        """
        return f"{self.first_name} {self.last_name}"

    def is_pending(self) -> bool:
        """Return whether the application is still waiting for a decision.

        Returns:
            bool: ``True`` while it is pending.
        """
        return self.status is HcaApplicationStatus.PENDING
