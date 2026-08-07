from __future__ import annotations

# Standard library imports
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTSkillTypeUpdateRequestInvalidDescription,
    MTSkillTypeUpdateRequestInvalidIsActive,
    MTSkillTypeUpdateRequestInvalidLabel,
)


class SkillTypeUpdateRequest(BaseModel):
    """The payload changing what a skill-catalogue entry says.

    Attributes:
        label (Optional[str]): The display name.
        description (Optional[str]): What the skill is.
        is_active (Optional[bool]): Whether it may still be required or
            declared.

    Notes:
        **``code`` is absent, so it cannot be changed at all.** It is what
        every assistant's declared skill and every intervention type's
        requirement is matched on; renaming it would leave a workforce holding
        skills for a code that no longer exists and quietly un-skill all of
        them on the next planning run. The screen shows the field locked, but
        the rule lives here — a locked input is a courtesy, not a control. This
        mirrors
        :class:`~models.schemas.requests.catalog.certification_type_update_request.CertificationTypeUpdateRequest`,
        and for the same reason.

        **A field left out and a field set to ``None`` are different
        requests.** Clearing ``description`` is a real edit; omitting it means
        "leave it alone". Optional fields alone cannot tell those apart, so the
        route reads ``model_dump(exclude_unset=True)`` and applies only what
        was actually sent.
    """

    label: Optional[str] = Field(default=None, description="The display name.")
    description: Optional[str] = Field(
        default=None, description="What the skill is."
    )
    is_active: Optional[bool] = Field(
        default=None, description="Whether it may still be required or declared."
    )

    @field_validator("label", mode="before")
    def validate_label(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``label`` is absent or a non-empty display name.

        Args:
            value (Optional[str]): Raw ``label`` value.

        Returns:
            Optional[str]: The stripped label, or ``None`` when not sent.

        Raises:
            MTSkillTypeUpdateRequestInvalidLabel: If ``value`` is present but
                blank once stripped, or is not a string.

        Notes:
            ``None`` passes because it means "not sent". A blank string does
            not: the label is the only human-readable thing about an entry, and
            one without it shows on an assistant's own screen as an empty
            option nobody can pick with any confidence.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTSkillTypeUpdateRequestInvalidLabel(
                f"Invalid label: {value!r}. Must be a non-empty display name."
            )
        return value.strip()

    @field_validator("description", mode="before")
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``description`` is absent or text.

        Args:
            value (Optional[str]): Raw ``description`` value.

        Returns:
            Optional[str]: The stripped description, or ``None``.

        Raises:
            MTSkillTypeUpdateRequestInvalidDescription: If ``value`` is neither
                ``None`` nor a string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTSkillTypeUpdateRequestInvalidDescription(
                f"Invalid description: {value!r}. Must be text."
            )
        return value.strip()

    @field_validator("is_active", mode="before")
    def validate_is_active(cls, value: Union[bool, str, int, None]) -> Optional[bool]:
        """Validates that ``is_active`` is absent or a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw ``is_active`` value.

        Returns:
            Optional[bool]: The flag, or ``None`` when not sent.

        Raises:
            MTSkillTypeUpdateRequestInvalidIsActive: If ``value`` is neither
                ``None`` nor a boolean.

        Notes:
            Strings are refused rather than coerced. ``"false"`` is truthy, and
            a retirement read as "still in use" would leave an obsolete skill
            on offer with nothing on screen to say the request had not taken.
        """
        if value is None:
            return None
        if not isinstance(value, bool):
            raise MTSkillTypeUpdateRequestInvalidIsActive(
                f"Invalid is_active: {value!r}. Must be true or false."
            )
        return value
