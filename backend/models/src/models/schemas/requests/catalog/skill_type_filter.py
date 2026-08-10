from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Type, Union

# Third-party imports
from pydantic import Field, field_validator

# First-party imports
from models.base.entity_filter import EntityFilter
from models.base.exceptions import MTInvalidEntityFilterException
from models.schemas.exceptions import (
    MTSkillTypeFilterInvalidFlag,
    MTSkillTypeFilterInvalidFragment,
)


class SkillTypeFilter(EntityFilter):
    """What narrows the skill catalogue on the way out of the API.

    Attributes:
        search (Optional[str]): Fragment matched against the code, the label
            and the description.
        code (Optional[str]): Fragment matched against the code alone.
        label (Optional[str]): Fragment matched against the label alone.
        is_active (Optional[bool]): Restrict to entries still in use, or to
            those retired.

    Notes:
        - ``is_active`` is a **three-state** filter over the top of the
          endpoint's older ``include_inactive`` switch. Unset, the endpoint
          behaves exactly as it always did — active entries only — so no
          existing caller changes behaviour; set, it wins, which is the only way
          to ask for the retired entries *on their own*.
        - A catalogue entry is retired rather than deleted, because a quote line
          written against it still has to print. That makes "show me what we
          stopped offering" a real question, and one nothing could ask before.
    """

    INVALID_FRAGMENT: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTSkillTypeFilterInvalidFragment
    )
    INVALID_FLAG: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTSkillTypeFilterInvalidFlag
    )

    search: Optional[str] = Field(
        default=None,
        description="Fragment matched against code, label and description.",
    )
    code: Optional[str] = Field(default=None, description="Fragment of the code.")
    label: Optional[str] = Field(default=None, description="Fragment of the label.")
    is_active: Optional[bool] = Field(
        default=None, description="Whether the entry is still offered."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("search", "code", "label", mode="before")
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a text filter is absent or a usable fragment.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when empty.

        Raises:
            MTSkillTypeFilterInvalidFragment: If ``value`` is neither ``None``
                nor a string.
        """
        return cls.validate_fragment(value)

    @field_validator("is_active", mode="before")
    def validate_flags(cls, value: Union[bool, str, int, None]) -> Optional[bool]:
        """Validates that the active flag is absent or a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw flag value.

        Returns:
            Optional[bool]: The flag, or ``None`` when unset.

        Raises:
            MTSkillTypeFilterInvalidFlag: If ``value`` is neither ``None`` nor a
                boolean.
        """
        return cls.validate_flag(value)
