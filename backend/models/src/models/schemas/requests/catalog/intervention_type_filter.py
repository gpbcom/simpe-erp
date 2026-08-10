from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Type, Union

# Third-party imports
from pydantic import Field, field_validator

# First-party imports
from models.base.entity_filter import EntityFilter
from models.base.exceptions import MTInvalidEntityFilterException
from models.enums import ServiceCategory
from models.schemas.exceptions import (
    MTInterventionTypeFilterInvalidCategory,
    MTInterventionTypeFilterInvalidFlag,
    MTInterventionTypeFilterInvalidFragment,
)


class InterventionTypeFilter(EntityFilter):
    """What narrows the service catalogue on the way out of the API.

    Attributes:
        search (Optional[str]): Fragment matched against the code, the name and
            the description.
        code (Optional[str]): Fragment matched against the code alone.
        name (Optional[str]): Fragment matched against the name alone.
        service_category (Optional[ServiceCategory]): Restrict to necessity or
            comfort services.
        is_active (Optional[bool]): Restrict to services still offered, or to
            those retired.

    Notes:
        - ``service_category`` is the one filter here with money attached: a
          necessity is VAT-rated differently from a comfort service, and an
          accountant checking a quote is looking at exactly this split.
        - ``is_active`` is a **three-state** filter over the top of the
          endpoint's older ``include_inactive`` switch. Unset, the endpoint
          behaves exactly as it always did — active services only — so no
          existing caller changes behaviour; set, it wins, which is the only way
          to ask for the retired services *on their own*.
    """

    INVALID_FRAGMENT: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTInterventionTypeFilterInvalidFragment
    )
    INVALID_FLAG: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTInterventionTypeFilterInvalidFlag
    )

    search: Optional[str] = Field(
        default=None,
        description="Fragment matched against code, name and description.",
    )
    code: Optional[str] = Field(default=None, description="Fragment of the code.")
    name: Optional[str] = Field(default=None, description="Fragment of the name.")
    service_category: Optional[ServiceCategory] = Field(
        default=None, description="Restrict to necessity or comfort services."
    )
    is_active: Optional[bool] = Field(
        default=None, description="Whether the service is still offered."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("service_category", mode="before")
    def validate_service_category(
        cls, value: Union[str, ServiceCategory, None]
    ) -> Optional[ServiceCategory]:
        """Validates that ``service_category`` is absent or a known category.

        Args:
            value (Union[str, ServiceCategory, None]): Raw category.

        Returns:
            Optional[ServiceCategory]: The coerced category, or ``None``.

        Raises:
            MTInterventionTypeFilterInvalidCategory: If ``value`` is neither
                empty nor a known service category.
        """
        if value is None or value == "":
            return None
        if isinstance(value, ServiceCategory):
            return value
        try:
            return ServiceCategory(value)
        except ValueError:
            raise MTInterventionTypeFilterInvalidCategory(
                f"Invalid service_category: {value!r}. Must be one of: "
                f"{', '.join(ServiceCategory.values())}."
            ) from None

    @field_validator("search", "code", "name", mode="before")
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a text filter is absent or a usable fragment.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when empty.

        Raises:
            MTInterventionTypeFilterInvalidFragment: If ``value`` is neither
                ``None`` nor a string.
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
            MTInterventionTypeFilterInvalidFlag: If ``value`` is neither
                ``None`` nor a boolean.
        """
        return cls.validate_flag(value)
