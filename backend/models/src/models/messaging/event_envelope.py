from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Dict, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_serializer, field_validator

# First-party imports
from models.messaging.exceptions import (
    MTEventEnvelopeInvalidPayload,
    MTEventEnvelopeInvalidRoutingKey,
    MTEventEnvelopeInvalidTimestamp,
)


class EventEnvelope(BaseModel):
    """One message on the broker: what happened, and enough to act on it.

    Attributes:
        routing_key (str): The topic the event was published under.
        payload (Dict[str, JsonValue]): The event's own fields.
        occurred_at (Optional[datetime]): When the event happened.

    Notes:
        - Every message on the exchange has this shape, so a consumer can log,
          retry and dead-letter one without understanding it. Only the handler
          that claims a routing key needs to know what is inside ``payload``.
        - The payload carries **identifiers, not records**. A message naming
          quote ``q-1`` is still correct when the consumer reads it a minute
          later; a message carrying a copy of the quote is a snapshot that may
          already be wrong, and the consumer would have no way to tell.
        - ``occurred_at`` is when the *event* happened, which is not when the
          message is handled. A queue that backed up overnight must not make
          yesterday's submissions look like this morning's.
    """

    routing_key: str = Field(description="The topic the event was published under.")
    payload: Dict[str, JsonValue] = Field(
        default_factory=dict,
        description="The event's own fields.",
    )
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="When the event happened.",
    )

    @field_validator("routing_key", mode="before")
    def validate_routing_key(cls, value: Optional[str]) -> str:
        """Validates that ``routing_key`` is a non-empty dotted string.

        Args:
            value (Optional[str]): Raw routing key.

        Returns:
            str: The stripped routing key.

        Raises:
            MTEventEnvelopeInvalidRoutingKey: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTEventEnvelopeInvalidRoutingKey(
                f"Invalid routing_key: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("payload", mode="before")
    def validate_payload(
        cls, value: Optional[Dict[str, JsonValue]]
    ) -> Dict[str, JsonValue]:
        """Validates that ``payload`` is a mapping.

        Args:
            value (Optional[Dict[str, JsonValue]]): Raw payload.

        Returns:
            Dict[str, JsonValue]: The payload, or an empty mapping.

        Raises:
            MTEventEnvelopeInvalidPayload: If ``value`` is not a mapping.
        """
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise MTEventEnvelopeInvalidPayload(
                f"Invalid payload: {value!r}. Must be a mapping."
            )
        return value

    @field_validator("occurred_at", mode="before")
    def validate_occurred_at(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that ``occurred_at`` is datetime-like or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic.

        Raises:
            MTEventEnvelopeInvalidTimestamp: If ``value`` is neither ``None``
                nor datetime-like.
        """
        if value is None:
            return None
        if isinstance(value, (str, datetime)):
            return value
        raise MTEventEnvelopeInvalidTimestamp(
            f"Invalid occurred_at: {value!r}. Must be a datetime, an ISO "
            f"string, or None."
        )

    @field_serializer("occurred_at")
    def serialize_occurred_at(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize the timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    def string_field(self, name: str) -> Optional[str]:
        """Return one payload field, when it is a usable string.

        Args:
            name (str): The field to read.

        Returns:
            Optional[str]: The value, or ``None`` when absent or not a string.

        Notes:
            A consumer reads a message it did not build, possibly written by an
            older version of the publisher. Reaching into ``payload`` directly
            would make every handler responsible for the same three checks; this
            makes a malformed field indistinguishable from a missing one, which
            is what the handler wants either way.
        """
        value = self.payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
