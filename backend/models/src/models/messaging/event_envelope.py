from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import ClassVar, Dict, FrozenSet, Optional

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_serializer, field_validator

# First-party imports
from models.messaging.exceptions import (
    MTEventEnvelopeInvalidPayload,
    MTEventEnvelopeInvalidRoutingKey,
    MTEventEnvelopeInvalidTimestamp,
    MTEventEnvelopeInvalidTraceparent,
)


class EventEnvelope(BaseModel):
    """One message on the broker: what happened, and enough to act on it.

    Attributes:
        TRACEPARENT_FIELDS (ClassVar[int]): How many fields a traceparent has.
        VERSION_LENGTH (ClassVar[int]): Characters in its version field.
        TRACE_ID_LENGTH (ClassVar[int]): Characters in its trace id.
        SPAN_ID_LENGTH (ClassVar[int]): Characters in its span id.
        FLAGS_LENGTH (ClassVar[int]): Characters in its flags field.
        HEX_DIGITS (ClassVar[FrozenSet[str]]): The digits it may use.
        routing_key (str): The topic the event was published under.
        payload (Dict[str, JsonValue]): The event's own fields.
        occurred_at (Optional[datetime]): When the event happened.
        traceparent (Optional[str]): W3C trace context, carried across the
            broker so a run traces back to the request that asked for it.

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
        - ``traceparent`` is the one field that is not about the event. Every
          instrumentation library propagates trace context over HTTP by itself
          and none of them does it over a broker, so without carrying it here a
          trace stops at ``POST /api/v1/planning/runs`` — and the thirty seconds
          that actually matter are attributed to nothing. It is **nullable**,
          so a message written by an older publisher, or by one with tracing
          switched off, still parses.
    """

    TRACEPARENT_FIELDS: ClassVar[int] = 4
    VERSION_LENGTH: ClassVar[int] = 2
    TRACE_ID_LENGTH: ClassVar[int] = 32
    SPAN_ID_LENGTH: ClassVar[int] = 16
    FLAGS_LENGTH: ClassVar[int] = 2
    HEX_DIGITS: ClassVar[FrozenSet[str]] = frozenset("0123456789abcdef")

    routing_key: str = Field(description="The topic the event was published under.")
    payload: Dict[str, JsonValue] = Field(
        default_factory=dict,
        description="The event's own fields.",
    )
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="When the event happened.",
    )
    traceparent: Optional[str] = Field(
        default=None,
        description="W3C trace context of whatever published this.",
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

    @field_validator("traceparent", mode="before")
    def validate_traceparent(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``traceparent`` is ``None`` or a W3C trace context.

        Args:
            value (Optional[str]): Raw trace context.

        Returns:
            Optional[str]: The stripped context, or ``None``.

        Raises:
            MTEventEnvelopeInvalidTraceparent: If ``value`` is neither ``None``
                nor a well-formed ``traceparent``.

        Notes:
            - The shape is fixed by the W3C specification: four hyphen-separated
              fields — version, a 32-character trace id, a 16-character span id
              and two flag characters, all lower-case hexadecimal.
            - Checked rather than trusted, because a malformed one is not inert.
              The extractor would ignore it and start a *new* trace, so the solve
              would appear to have begun on its own with no request behind it —
              which reads as a complete picture and is not one.
            - An all-zero trace or span id is refused for the same reason: the
              specification says both are invalid, and a collector that follows it
              drops the span without telling anybody.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTEventEnvelopeInvalidTraceparent(
                f"Invalid traceparent: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        parts = stripped.split("-")
        if len(parts) != cls.TRACEPARENT_FIELDS:
            raise MTEventEnvelopeInvalidTraceparent(
                f"Invalid traceparent: {stripped!r}. Must be four "
                f"hyphen-separated fields."
            )
        version, trace_id, span_id, flags = parts
        lengths = (
            len(version) == cls.VERSION_LENGTH,
            len(trace_id) == cls.TRACE_ID_LENGTH,
            len(span_id) == cls.SPAN_ID_LENGTH,
            len(flags) == cls.FLAGS_LENGTH,
        )
        if not all(lengths):
            raise MTEventEnvelopeInvalidTraceparent(
                f"Invalid traceparent: {stripped!r}. Fields must be "
                f"{cls.VERSION_LENGTH}, {cls.TRACE_ID_LENGTH}, "
                f"{cls.SPAN_ID_LENGTH} and {cls.FLAGS_LENGTH} characters."
            )
        if any(
            character not in cls.HEX_DIGITS for character in stripped.replace("-", "")
        ):
            raise MTEventEnvelopeInvalidTraceparent(
                f"Invalid traceparent: {stripped!r}. Must be lower-case hexadecimal."
            )
        if set(trace_id) == {"0"} or set(span_id) == {"0"}:
            raise MTEventEnvelopeInvalidTraceparent(
                f"Invalid traceparent: {stripped!r}. "
                f"An all-zero trace or span id is not a valid one."
            )
        return stripped

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
        cls,
        value: Optional[
            str,
            datetime,
        ],
    ) -> Optional[
        str,
        datetime,
    ]:
        """Validates that ``occurred_at`` is datetime-like or ``None``.

        Args:
            value (Optional[str, datetime,]): Raw timestamp.

        Returns:
            Optional[str, datetime,]: The value handed back for Pydantic.

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
    def serialize_occurred_at(self, value: Optional[datetime]) -> Optional[str]:  # noqa: E501
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
