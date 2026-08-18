from __future__ import annotations

# Standard library imports
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import RegistrationStatus
from models.schemas.exceptions import (
    MTCustomerFilterInvalidFlag,
    MTCustomerFilterInvalidFragment,
    MTCustomerFilterInvalidStatus,
)


class CustomerFilter(BaseModel):
    """What narrows the customer book on the way out of the API.

    Attributes:
        search (Optional[str]): Fragment matched against the names, the email
            address and the town.
        status (Optional[RegistrationStatus]): Restrict to one registration
            status.
        city (Optional[str]): Fragment matched against the town.
        postal_code (Optional[str]): Fragment matched against the postcode.
        email (Optional[str]): Fragment matched against the email address.
        phone (Optional[str]): Fragment matched against the telephone number.
        has_ongoing_arrangement (Optional[bool]): Restrict to customers who
            currently have work being delivered, or to those who do not.
        is_geocoded (Optional[bool]): Restrict to customers whose address
            resolved, or to those whose did not.

    Notes:
        - **A model rather than eight query parameters.** The endpoint took four
          and was already at the edge of readable. A ninth would have made the
          signature the longest thing in the router. Gathering them here also
          puts the validation somewhere it can be tested without an HTTP client.
        - **Every field is optional, and ``None`` means "not applied".** That is
          the difference between a filter and a search form: a caller sends the
          two boxes they filled in, not eight, and the ones they left alone must
          not silently narrow anything.
        - **A blank string is also "not applied".** An input box the user typed
          in and then cleared sends ``""``, and reading that as "match customers
          whose town is the empty string" would answer nobody. The validators
          normalise it to ``None`` so the repository has one case to handle.
        - ``search`` overlaps ``city`` and ``email`` deliberately. It is the one
          box somebody types a name into without deciding which field it is;
          the named filters are for when they have decided.
    """

    search: Optional[str] = Field(
        default=None,
        description="Fragment matched against names, email and town.",
    )
    status: Optional[RegistrationStatus] = Field(
        default=None,
        description="Restrict to one registration status.",
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
    has_ongoing_arrangement: Optional[bool] = Field(
        default=None,
        description="Whether the customer has work currently being delivered.",
    )
    is_geocoded: Optional[bool] = Field(
        default=None,
        description="Whether the customer's address resolved to a coordinate.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("status", mode="before")
    def validate_status(
        cls, value: Union[str, RegistrationStatus, None]
    ) -> Optional[RegistrationStatus]:
        """Validates that ``status`` is absent or a known status.

        Args:
            value (Union[str, RegistrationStatus, None]): Raw status value.

        Returns:
            Optional[RegistrationStatus]: The coerced status, or ``None``.

        Raises:
            MTCustomerFilterInvalidStatus: If ``value`` is neither empty nor a
                known registration status.

        Notes:
            Unlike the customer's own field, ``None`` does **not** fall back to
            a default here: a filter nobody set must not quietly become a filter
            on prospects.
        """
        if value is None or value == "":
            return None
        if isinstance(value, RegistrationStatus):
            return value
        try:
            return RegistrationStatus(value)
        except ValueError:
            raise MTCustomerFilterInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(RegistrationStatus.values())}."
            ) from None

    @field_validator("search", "city", "postal_code", "email", "phone", mode="before")
    def validate_fragment(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a text filter is absent or a usable fragment.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when it is empty.

        Raises:
            MTCustomerFilterInvalidFragment: If ``value`` is neither ``None``
                nor a string.

        Notes:
            Stripped and emptied to ``None`` so the repository never has to ask
            whether a filter is present *and* whether it is meaningful.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCustomerFilterInvalidFragment(
                f"Invalid filter fragment: {value!r}. Must be a string or None."
            )
        return value.strip() or None

    @field_validator("has_ongoing_arrangement", "is_geocoded", mode="before")
    def validate_flag(cls, value: Union[bool, str, int, None]) -> Optional[bool]:
        """Validates that a three-state flag is absent or a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw flag value.

        Returns:
            Optional[bool]: The flag, or ``None`` when the filter is unset.

        Raises:
            MTCustomerFilterInvalidFlag: If ``value`` is neither ``None`` nor a
                boolean.

        Notes:
            - **Three states, not two.** ``None`` is "do not filter on this",
              ``False`` is "only those where it is false" — and conflating them
              would make an unticked box hide every customer who *has* an
              arrangement.
            - Strings are refused rather than coerced: ``"false"`` is truthy, and
              a flag read the wrong way round answers the opposite question in
              silence.
        """
        if value is None:
            return None
        if not isinstance(value, bool):
            raise MTCustomerFilterInvalidFlag(
                f"Invalid filter flag: {value!r}. Must be true, false or None."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_empty(self) -> bool:
        """Return whether the filter narrows anything at all.

        Returns:
            bool: ``True`` when every field is unset.

        Notes:
            Lets a caller log "listing every customer" rather than "listing
            customers matching nothing", which are opposite readings of the
            same empty filter.
        """
        return all(value is None for value in self.model_dump().values())
