from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_serializer, field_validator

# First-party imports
from models.catalog.exceptions import (
    MTCertificationTypeInvalidCode,
    MTCertificationTypeInvalidDate,
    MTCertificationTypeInvalidDescription,
    MTCertificationTypeInvalidId,
    MTCertificationTypeInvalidIsActive,
    MTCertificationTypeInvalidLabel,
)


class CertificationType(BaseModel):
    """A qualification the agency recognises, defined by a manager or an admin.

    Attributes:
        CODE_MAX_LENGTH (ClassVar[int]): Longest code accepted, matching the
            store's column width.
        id (Optional[str]): Identifier, populated on read from the store.
        code (str): Short stable key, upper-cased and unique across the
            catalogue.
        label (str): Display name, such as "Diplôme d'État d'Accompagnant
            Éducatif et Social".
        description (Optional[str]): Free-text description.
        is_active (bool): Whether the qualification may be required on a new
            intervention type or recorded against an assistant.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - **The code is the contract, not the label.** An assistant's
          qualification and an intervention type's requirement are matched on
          ``code``, so renaming the label is a cosmetic change while changing
          the code silently un-qualifies everybody who held it. That is why the
          two are separate fields rather than one name doing both jobs, and why
          the code is character-restricted.
        - Retired with ``is_active``, never deleted — exactly like
          :class:`~models.catalog.intervention_type.InterventionType`. A stored
          qualification still names its code, and removing the row would leave
          an assistant holding a certification nothing could describe.
    """

    CODE_MAX_LENGTH: ClassVar[int] = 32

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    code: str = Field(description="Short stable key, upper-cased and unique.")
    label: str = Field(description="Display name of the qualification.")
    description: Optional[str] = Field(
        default=None,
        description="Free-text description.",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the qualification may still be required or held.",
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
            MTCertificationTypeInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCertificationTypeInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("code", mode="before")
    def validate_code(cls, value: Optional[str]) -> str:
        """Validates that ``code`` is a non-empty alphanumeric key.

        Args:
            value (Optional[str]): Raw ``code`` value.

        Returns:
            str: The upper-cased key.

        Raises:
            MTCertificationTypeInvalidCode: If ``value`` is not a non-empty
                string of unaccented letters, digits, hyphens or underscores,
                or is longer than :attr:`CODE_MAX_LENGTH`.

        Notes:
            - Upper-cased on the way in so ``deaes`` and ``DEAES`` are the same
              qualification. Matching is a plain equality test in the solver's
              hot loop, and normalising at every comparison instead would make
             "did this person hold it?" depend on how somebody typed it.
            - **ASCII, deliberately, in a French domain whose labels are full of
              accents.** ``É`` passes :meth:`str.isalnum`, so restricting the
              alphabet takes an explicit test. The code travels into CSV exports
              and URLs, where an accent is escaped differently by every consumer
              and the same qualification comes back as two — and upper-casing an
              accented letter is not even well defined across every locale. The
              *label* is where the accents belong, and it keeps them.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCertificationTypeInvalidCode(
                f"Invalid code: {value!r}. Must be a non-empty string."
            )
        normalized = value.strip().upper()
        if len(normalized) > cls.CODE_MAX_LENGTH:
            raise MTCertificationTypeInvalidCode(
                f"Invalid code: {value!r}. Must be at most "
                f"{cls.CODE_MAX_LENGTH} characters."
            )
        if not all(
            (character.isascii() and character.isalnum()) or character in "-_"
            for character in normalized
        ):
            raise MTCertificationTypeInvalidCode(
                f"Invalid code: {value!r}. Must hold only unaccented "
                f"letters, digits, hyphens or underscores."
            )
        return normalized

    @field_validator("label", mode="before")
    def validate_label(cls, value: Optional[str]) -> str:
        """Validates that ``label`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``label`` value.

        Returns:
            str: The stripped display name.

        Raises:
            MTCertificationTypeInvalidLabel: If ``value`` is not a non-empty
                string.

        Notes:
            Accents and spaces are kept. The label is what a manager reads on
            the workforce screen, and the code already carries the machine-safe
            form of the same thing.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCertificationTypeInvalidLabel(
                f"Invalid label: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("description", mode="before")
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``description`` is ``None`` or a string.

        Args:
            value (Optional[str]): Raw ``description`` value.

        Returns:
            Optional[str]: The stripped description, or ``None`` when blank.

        Raises:
            MTCertificationTypeInvalidDescription: If ``value`` is neither
                ``None`` nor a string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCertificationTypeInvalidDescription(
                f"Invalid description: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        return stripped if stripped else None

    @field_validator("is_active", mode="before")
    def validate_is_active(cls, value: Union[bool, str, int, None]) -> bool:
        """Validates that ``is_active`` is a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw ``is_active`` value.
                ``None`` falls back to ``True``.

        Returns:
            bool: The validated flag.

        Raises:
            MTCertificationTypeInvalidIsActive: If ``value`` is neither ``None``
                nor a boolean.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTCertificationTypeInvalidIsActive(
                f"Invalid is_active: {value!r}. Must be true or false."
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
            MTCertificationTypeInvalidDate: If ``value`` is neither
                ``None`` nor a datetime-like value.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise MTCertificationTypeInvalidDate(
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

    ############################
    # Publicly Exposed Methods #
    ############################

    def describe(self) -> str:
        """Return a one-line description naming both the code and the label.

        Returns:
            str: For instance ``"DEAES (Diplôme d'État d'Accompagnant Éducatif
            et Social)"``.

        Notes:
            Used in the planner's unplaced-work diagnosis. A manager told only
            "DEAES is missing" has to go and look the code up. Naming both is
            what makes the message actionable where it is read.
        """
        return f"{self.code} ({self.label})"
