from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_serializer, field_validator

# First-party imports
from models.enums import NotificationKind
from models.notifications.exceptions import (
    MTNotificationInvalidDate,
    MTNotificationInvalidId,
    MTNotificationInvalidKind,
    MTNotificationInvalidReadState,
    MTNotificationInvalidRecipient,
    MTNotificationInvalidTitle,
)


class Notification(BaseModel):
    """Something that happened, addressed to one account.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        recipient_id (str): The account it is addressed to.
        kind (NotificationKind): What it is about.
        title (str): The one-line summary a list shows.
        body (Optional[str]): The detail, shown when the row is opened.
        quote_id (Optional[str]): The quote it points at, when it points at one.
        is_read (bool): Whether the recipient has seen it.
        created_at (Optional[datetime]): When the event happened.
        read_at (Optional[datetime]): When the recipient marked it read.

    Notes:
        - **One row per recipient, not one row per event.** A quote submitted to
          an agency with three managers produces three notifications. Storing
          one event and computing recipients on read would make "have I read
          this?" unanswerable — read state belongs to a person, and two managers
          must be able to disagree about whether they have dealt with something.
        - The notification is a **record**, not a delivery mechanism. It is
          written to the database first and pushed over the wire second, so a
          reader who was offline, or whose stream dropped, still finds it
          waiting. A design that only pushed would lose the notification exactly
          when it matters most — overnight, when nobody is watching.
        - The text is stored, not templated at read time. What a manager was
          told is what they were told; regenerating it later would rewrite
          history after a customer is renamed or a quote is repriced.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    recipient_id: str = Field(description="The account it is addressed to.")
    kind: NotificationKind = Field(description="What it is about.")
    title: str = Field(description="The one-line summary a list shows.")
    body: Optional[str] = Field(
        default=None,
        description="The detail, shown when the row is opened.",
    )
    quote_id: Optional[str] = Field(
        default=None,
        description="The quote it points at, when it points at one.",
    )
    is_read: bool = Field(
        default=False,
        description="Whether the recipient has seen it.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="When the event happened.",
    )
    read_at: Optional[datetime] = Field(
        default=None,
        description="When the recipient marked it read.",
    )

    @field_validator("id", "quote_id", mode="before")
    def validate_optional_identifier(cls, value: Optional[str]) -> Optional[str]:
        """Validates that an optional identifier is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw identifier.

        Returns:
            Optional[str]: The stripped identifier, or ``None``.

        Raises:
            MTNotificationInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTNotificationInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("recipient_id", mode="before")
    def validate_recipient_id(cls, value: Optional[str]) -> str:
        """Validates that ``recipient_id`` is a non-empty string.

        Args:
            value (Optional[str]): Raw recipient identifier.

        Returns:
            str: The stripped identifier.

        Raises:
            MTNotificationInvalidRecipient: If ``value`` is not a non-empty
                string.

        Notes:
            Required, and refused rather than defaulted. A notification with no
            recipient is one nobody will ever see, and it fails silently — it
            looks exactly like the event never happening.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTNotificationInvalidRecipient(
                f"Invalid recipient_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("kind", mode="before")
    def validate_kind(
        cls, value: Union[str, NotificationKind, None]
    ) -> NotificationKind:
        """Validates that ``kind`` is a known notification kind.

        Args:
            value (Union[str, NotificationKind, None]): Raw kind.

        Returns:
            NotificationKind: The coerced kind.

        Raises:
            MTNotificationInvalidKind: If ``value`` is not a known kind.
        """
        if isinstance(value, NotificationKind):
            return value
        try:
            return NotificationKind(value)
        except ValueError:
            raise MTNotificationInvalidKind(
                f"Invalid kind: {value!r}. Must be one of: "
                f"{', '.join(NotificationKind.values())}."
            ) from None

    @field_validator("title", mode="before")
    def validate_title(cls, value: Optional[str]) -> str:
        """Validates that ``title`` is a non-empty string.

        Args:
            value (Optional[str]): Raw title.

        Returns:
            str: The stripped title.

        Raises:
            MTNotificationInvalidTitle: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTNotificationInvalidTitle(
                f"Invalid title: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("is_read", mode="before")
    def validate_is_read(cls, value: Optional[bool]) -> bool:
        """Validates that ``is_read`` is a boolean.

        Args:
            value (Optional[bool]): Raw read flag.

        Returns:
            bool: The validated flag.

        Raises:
            MTNotificationInvalidReadState: If ``value`` is not a boolean.

        Notes:
            Rejected rather than coerced. This flag drives the unread badge, and
            a truthy string would clear somebody's queue on their behalf.
        """
        if not isinstance(value, bool):
            raise MTNotificationInvalidReadState(
                f"Invalid is_read: {value!r}. Must be a boolean."
            )
        return value

    @field_validator("created_at", "read_at", mode="before")
    def validate_timestamps(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a timestamp is datetime-like or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic.

        Raises:
            MTNotificationInvalidDate: If ``value`` is neither ``None`` nor
                datetime-like.
        """
        if value is None:
            return None
        if isinstance(value, (str, datetime)):
            return value
        raise MTNotificationInvalidDate(
            f"Invalid timestamp: {value!r}. Must be a datetime, an ISO string, or None."
        )

    @field_serializer("created_at", "read_at")
    def serialize_timestamp(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    def is_actionable(self) -> bool:
        """Return whether the reader can be sent somewhere from this.

        Returns:
            bool: ``True`` when the notification points at a quote that exists.

        Notes:
            A client uses this to decide whether the row is a link or plain
            text. A quote-kind notification that lost its ``quote_id`` is not
            actionable, and rendering it as a link would produce a dead one.
        """
        return self.kind.concerns_a_quote() and self.quote_id is not None
