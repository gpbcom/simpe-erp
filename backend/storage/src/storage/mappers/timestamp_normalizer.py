from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Optional


class TimestampNormalizer:
    """Guarantees that timestamps leaving the store are timezone-aware UTC.

    Notes:
        - Every timestamp is written as timezone-aware UTC, but not every backend
          gives it back that way. PostgreSQL's ``TIMESTAMPTZ`` preserves the
          offset; SQLite has no timezone type at all and returns a naive value.
          Left alone, the same code would yield aware datetimes in production and
          naive ones under test, and the two cannot even be compared — Python
          raises on ``aware < naive``.
        - Attaching UTC to a naive value is sound rather than a guess: the write
          path is the only producer of these columns, and it always writes UTC.
        - A value that already carries an offset is converted rather than
          overwritten, so a backend returning ``+02:00`` yields the same instant
          rather than a time two hours wrong.
    """

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_utc(self, value: Optional[datetime]) -> Optional[datetime]:
        """Return a timestamp as timezone-aware UTC.

        Args:
            value (Optional[datetime]): The timestamp to normalize.

        Returns:
            Optional[datetime]: The timestamp in UTC, or ``None`` when the
            input was ``None``.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
