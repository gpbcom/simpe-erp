from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Type, Union

# Third-party imports
from pydantic import Field, field_validator

# First-party imports
from models.base.entity_filter import EntityFilter
from models.base.exceptions import MTInvalidEntityFilterException
from models.enums import ContractType
from models.schemas.exceptions import (
    MTHcaFilterInvalidContractType,
    MTHcaFilterInvalidFlag,
    MTHcaFilterInvalidFragment,
)


class HcaFilter(EntityFilter):
    """What narrows the assistant list on the way out of the API.

    Attributes:
        search (Optional[str]): Fragment matched against the names, the email
            address and the town.
        contract_type (Optional[ContractType]): Restrict to one contract type.
        city (Optional[str]): Fragment matched against the town.
        postal_code (Optional[str]): Fragment matched against the postcode.
        email (Optional[str]): Fragment matched against the email address.
        phone (Optional[str]): Fragment matched against the telephone number.
        field_employee (Optional[bool]): Restrict to assistants who go out on
            the rounds, or to those who do not.
        is_geocoded (Optional[bool]): Restrict to assistants whose address
            resolved, or to those whose did not.
        has_photo (Optional[bool]): Restrict to assistants who have a portrait.

    Notes:
        - Deliberately shaped like the customer filter. A manager narrowing a
          list of people is doing the same thing whichever list it is, and two
          screens that answer the same question with different boxes are two
          screens somebody has to learn.
        - ``field_employee`` matters more here than it looks: an assistant taken
          off the rounds is invisible to the planner, and "who is actually
          available this week" is the question this filter exists to answer.
        - ``is_geocoded`` is the other half of that. An assistant whose address
          never resolved cannot be routed, and they are otherwise indis-
          tinguishable from one who simply has no visits yet.
    """

    INVALID_FRAGMENT: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTHcaFilterInvalidFragment
    )
    INVALID_FLAG: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTHcaFilterInvalidFlag
    )

    search: Optional[str] = Field(
        default=None,
        description="Fragment matched against names, email and town.",
    )
    contract_type: Optional[ContractType] = Field(
        default=None, description="Restrict to one contract type."
    )
    city: Optional[str] = Field(default=None, description="Fragment of the town.")
    postal_code: Optional[str] = Field(
        default=None, description="Fragment of the postcode."
    )
    email: Optional[str] = Field(
        default=None, description="Fragment of the email address."
    )
    phone: Optional[str] = Field(
        default=None, description="Fragment of the telephone number."
    )
    field_employee: Optional[bool] = Field(
        default=None, description="Whether the assistant goes out on the rounds."
    )
    is_geocoded: Optional[bool] = Field(
        default=None, description="Whether the address resolved to a coordinate."
    )
    has_photo: Optional[bool] = Field(
        default=None, description="Whether the assistant has a portrait."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("contract_type", mode="before")
    def validate_contract_type(
        cls, value: Union[str, ContractType, None]
    ) -> Optional[ContractType]:
        """Validates that ``contract_type`` is absent or a known type.

        Args:
            value (Union[str, ContractType, None]): Raw contract type.

        Returns:
            Optional[ContractType]: The coerced type, or ``None``.

        Raises:
            MTHcaFilterInvalidContractType: If ``value`` is neither empty nor a
                known contract type.
        """
        if value is None or value == "":
            return None
        if isinstance(value, ContractType):
            return value
        try:
            return ContractType(value)
        except ValueError:
            raise MTHcaFilterInvalidContractType(
                f"Invalid contract_type: {value!r}. Must be one of: "
                f"{', '.join(ContractType.values())}."
            ) from None

    @field_validator("search", "city", "postal_code", "email", "phone", mode="before")
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a text filter is absent or a usable fragment.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when empty.

        Raises:
            MTHcaFilterInvalidFragment: If ``value`` is neither ``None`` nor a
                string.
        """
        return cls.validate_fragment(value)

    @field_validator("field_employee", "is_geocoded", "has_photo", mode="before")
    def validate_flags(cls, value: Union[bool, str, int, None]) -> Optional[bool]:
        """Validates that a three-state flag is absent or a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw flag value.

        Returns:
            Optional[bool]: The flag, or ``None`` when unset.

        Raises:
            MTHcaFilterInvalidFlag: If ``value`` is neither ``None`` nor a
                boolean.
        """
        return cls.validate_flag(value)
