from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_serializer, field_validator

# First-party imports
from models.catalog.exceptions import (
    MTSkillTypeInvalidCode,
    MTSkillTypeInvalidDate,
    MTSkillTypeInvalidDescription,
    MTSkillTypeInvalidId,
    MTSkillTypeInvalidIsActive,
    MTSkillTypeInvalidLabel,
)


class SkillType(BaseModel):
    """A skill the agency recognises, defined by a manager or an admin.

    Attributes:
        CODE_MAX_LENGTH (ClassVar[int]): Longest code accepted, matching the
            store's column width.
        id (Optional[str]): Identifier, populated on read from the store.
        code (str): Short stable key, upper-cased and unique across the
            catalogue.
        label (str): Display name, such as "Manipulation d'un lève-personne".
        description (Optional[str]): Free-text description.
        is_active (bool): Whether the skill may be required on a new
            intervention type or declared by an assistant.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - **A skill is not a certification, and the two catalogues are
          separate on purpose.** A certification is awarded by somebody else
          and a manager records it. A skill is what an assistant says they can
          do, and they enter it themselves. Folding them into one catalogue
          would mean either letting an assistant grant themselves a diploma or
          making them ask a manager to record that they speak Portuguese —
          and the planner has to be able to require one without requiring the
          other.
        - **The code is the contract, not the label.** An assistant's declared
          skill and an intervention type's requirement are matched on ``code``,
          so renaming the label is a cosmetic change while changing the code
          silently un-skills everybody who declared it. That is why the two are
          separate fields rather than one name doing both jobs, and why the
          code is character-restricted.
        - Retired with ``is_active``, never deleted — exactly like
          :class:`~models.catalog.certification_type.CertificationType`. A
          stored skill still names its code, and removing the row would leave
          an assistant holding a skill nothing could describe.
    """

    CODE_MAX_LENGTH: ClassVar[int] = 32

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    code: str = Field(description="Short stable key, upper-cased and unique.")
    label: str = Field(description="Display name of the skill.")
    description: Optional[str] = Field(
        default=None,
        description="Free-text description.",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the skill may still be required or declared.",
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
            MTSkillTypeInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTSkillTypeInvalidId(
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
            MTSkillTypeInvalidCode: If ``value`` is not a non-empty string of
                unaccented letters, digits, hyphens or underscores, or is
                longer than :attr:`CODE_MAX_LENGTH`.

        Notes:
            - Upper-cased on the way in so ``leve-personne`` and
              ``LEVE-PERSONNE`` are the same skill. Matching is a plain
              equality test in the solver's hot loop, and normalising at every
              comparison instead would make "can this person do it?" depend on
              how somebody typed it.
            - **ASCII, deliberately, in a French domain whose labels are full
              of accents**, for the same reasons as
              :meth:`~models.catalog.certification_type.CertificationType.validate_code`:
              ``É`` passes :meth:`str.isalnum`, the code travels into CSV
              exports and URLs where an accent comes back as two distinct
              skills, and upper-casing an accented letter is not well defined
              across every locale. The *label* is where the accents belong.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTSkillTypeInvalidCode(
                f"Invalid code: {value!r}. Must be a non-empty string."
            )
        normalized = value.strip().upper()
        if len(normalized) > cls.CODE_MAX_LENGTH:
            raise MTSkillTypeInvalidCode(
                f"Invalid code: {value!r}. Must be at most "
                f"{cls.CODE_MAX_LENGTH} characters."
            )
        if not all(
            (character.isascii() and character.isalnum()) or character in "-_"
            for character in normalized
        ):
            raise MTSkillTypeInvalidCode(
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
            MTSkillTypeInvalidLabel: If ``value`` is not a non-empty string.

        Notes:
            Accents and spaces are kept. The label is what an assistant picks
            from on their own account screen, and the code already carries the
            machine-safe form of the same thing.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTSkillTypeInvalidLabel(
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
            MTSkillTypeInvalidDescription: If ``value`` is neither ``None`` nor
                a string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTSkillTypeInvalidDescription(
                f"Invalid description: {value!r}. "  # noqa: E501
                "Must be a string or None."
            )
        stripped = value.strip()
        return stripped if stripped else None

    @field_validator("is_active", mode="before")
    def validate_is_active(cls, value: Optional[bool, str, int]) -> bool:
        """Validates that ``is_active`` is a boolean.

        Args:
            value (Optional[bool, str, int]): Raw ``is_active`` value.
                ``None`` falls back to ``True``.

        Returns:
            bool: The validated flag.

        Raises:
            MTSkillTypeInvalidIsActive: If ``value`` is neither ``None`` nor a
                boolean.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTSkillTypeInvalidIsActive(
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
            MTSkillTypeInvalidDate: If ``value`` is neither ``None`` nor a
                datetime-like value.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise MTSkillTypeInvalidDate(
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
            str: For instance ``"LEVE-PERSONNE (Manipulation d'un
            lève-personne)"``.

        Notes:
            Used in the planner's unplaced-work diagnosis. A manager told only
            "LEVE-PERSONNE is missing" has to go and look the code up. Naming
            both is what makes the message actionable where it is read.
        """
        return f"{self.code} ({self.label})"
