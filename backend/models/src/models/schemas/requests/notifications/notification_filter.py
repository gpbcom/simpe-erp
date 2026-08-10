from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Type, Union

# Third-party imports
from pydantic import Field, field_validator

# First-party imports
from models.base.entity_filter import EntityFilter
from models.base.exceptions import MTInvalidEntityFilterException
from models.enums import NotificationKind
from models.schemas.exceptions import (
    MTNotificationFilterInvalidFlag,
    MTNotificationFilterInvalidFragment,
    MTNotificationFilterInvalidKind,
)


class NotificationFilter(EntityFilter):
    """What narrows one account's notifications on the way out of the API.

    Attributes:
        search (Optional[str]): Fragment matched against the title and the body.
        kind (Optional[NotificationKind]): Restrict to one kind of event.
        is_read (Optional[bool]): Restrict to those already read, or to those
            not.

    Notes:
        - **There is no recipient filter, and that is the point.** The account
          whose notifications these are comes from the credential, exactly as it
          did before this filter existed. A field naming a recipient would be
          the whole of a cross-account read, so the model cannot carry one.
        - ``is_read`` is a three-state filter over the top of the endpoint's
          older ``unread_only`` switch. Unset, the endpoint behaves as it always
          did; set, it wins — which is the only way to ask for the ones already
          read, a thing nothing could do before.
    """

    INVALID_FRAGMENT: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTNotificationFilterInvalidFragment
    )
    INVALID_FLAG: ClassVar[Type[MTInvalidEntityFilterException]] = (
        MTNotificationFilterInvalidFlag
    )

    search: Optional[str] = Field(
        default=None, description="Fragment matched against the title and body."
    )
    kind: Optional[NotificationKind] = Field(
        default=None, description="Restrict to one kind of event."
    )
    is_read: Optional[bool] = Field(
        default=None, description="Whether the notification has been read."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("kind", mode="before")
    def validate_kind(
        cls, value: Union[str, NotificationKind, None]
    ) -> Optional[NotificationKind]:
        """Validates that ``kind`` is absent or a known notification kind.

        Args:
            value (Union[str, NotificationKind, None]): Raw kind value.

        Returns:
            Optional[NotificationKind]: The coerced kind, or ``None``.

        Raises:
            MTNotificationFilterInvalidKind: If ``value`` is neither empty nor
                a known notification kind.
        """
        if value is None or value == "":
            return None
        if isinstance(value, NotificationKind):
            return value
        try:
            return NotificationKind(value)
        except ValueError:
            raise MTNotificationFilterInvalidKind(
                f"Invalid kind: {value!r}. Must be one of: "
                f"{', '.join(NotificationKind.values())}."
            ) from None

    @field_validator("search", mode="before")
    def validate_text(cls, value: Optional[str]) -> Optional[str]:
        """Validates that the search filter is absent or a usable fragment.

        Args:
            value (Optional[str]): Raw fragment.

        Returns:
            Optional[str]: The stripped fragment, or ``None`` when empty.

        Raises:
            MTNotificationFilterInvalidFragment: If ``value`` is neither
                ``None`` nor a string.
        """
        return cls.validate_fragment(value)

    @field_validator("is_read", mode="before")
    def validate_flags(cls, value: Union[bool, str, int, None]) -> Optional[bool]:
        """Validates that the read flag is absent or a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw flag value.

        Returns:
            Optional[bool]: The flag, or ``None`` when unset.

        Raises:
            MTNotificationFilterInvalidFlag: If ``value`` is neither ``None``
                nor a boolean.
        """
        return cls.validate_flag(value)
