from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import DatabaseStatus, ProbeStatus
from models.schemas.exceptions import (
    MTReadinessResponseInvalidDatabase,
    MTReadinessResponseInvalidStatus,
)


class ReadinessResponse(BaseModel):
    """What the readiness probe reports.

    Attributes:
        status (ProbeStatus): Whether the instance can serve traffic.
        database (DatabaseStatus): Whether the store answered.

    Notes:
        Both halves are reported, not just the verdict. A 503 that says only
        "not ready" sends an operator to the logs; one that names the database
        as unreachable has already answered the first question they would ask.
    """

    status: ProbeStatus = Field(description="Whether the instance is ready.")
    database: DatabaseStatus = Field(description="Whether the store answered.")

    @field_validator("status", mode="before")
    def validate_status(cls, value: Union[str, ProbeStatus, None]) -> ProbeStatus:
        """Validates that ``status`` is a known probe status.

        Args:
            value (Union[str, ProbeStatus, None]): Raw ``status`` value.

        Returns:
            ProbeStatus: The coerced status.

        Raises:
            MTReadinessResponseInvalidStatus: If ``value`` is not a known
                status.
        """
        if isinstance(value, ProbeStatus):
            return value
        try:
            return ProbeStatus(value)
        except ValueError:
            raise MTReadinessResponseInvalidStatus(
                f"Invalid status: {value!r}. Must be one of: "
                f"{', '.join(ProbeStatus.values())}."
            ) from None

    @field_validator("database", mode="before")
    def validate_database(
        cls, value: Union[str, DatabaseStatus, None]
    ) -> DatabaseStatus:
        """Validates that ``database`` is a known database status.

        Args:
            value (Union[str, DatabaseStatus, None]): Raw ``database`` value.

        Returns:
            DatabaseStatus: The coerced status.

        Raises:
            MTReadinessResponseInvalidDatabase: If ``value`` is not a known
                status.
        """
        if isinstance(value, DatabaseStatus):
            return value
        try:
            return DatabaseStatus(value)
        except ValueError:
            raise MTReadinessResponseInvalidDatabase(
                f"Invalid database: {value!r}. Must be one of: "
                f"{', '.join(DatabaseStatus.values())}."
            ) from None
