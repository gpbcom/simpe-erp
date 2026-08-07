from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import UnplacedReason
from models.planning.planning_run.exceptions import (
    MTUnplacedRequirementInvalidDay,
    MTUnplacedRequirementInvalidDetail,
    MTUnplacedRequirementInvalidId,
    MTUnplacedRequirementInvalidName,
    MTUnplacedRequirementInvalidReason,
)


class UnplacedRequirement(BaseModel):
    """A piece of accepted work the planner could not schedule, and why.

    Attributes:
        requirement_id (str): The work that could not be placed.
        name (str): What the service is, for a message a planner can act on.
        customer_id (str): Whose work it is.
        day (date): The day it had to happen on.
        reason (UnplacedReason): Why it could not be placed.
        detail (Optional[str]): The specifics — the distance measured, the
            visit it clashes with.

    Notes:
        This exists so that a failed planning run says *what to change* rather
        than "infeasible". "No assistant lives within 30 km of Mme Durand" is a
        sentence a manager can act on by widening the radius or hiring;
        "INFEASIBLE" is not.

        Carries the name and the customer, not just an identifier, because the
        message is read by somebody who knows their customers by name and has
        never seen a UUID.
    """

    requirement_id: str = Field(description="The work that could not be placed.")
    name: str = Field(description="What the service is.")
    customer_id: str = Field(description="Whose work it is.")
    day: date = Field(description="The day it had to happen on.")
    reason: UnplacedReason = Field(description="Why it could not be placed.")
    detail: Optional[str] = Field(
        default=None, description="The specifics behind the reason."
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("requirement_id", "customer_id", mode="before")
    def validate_identifiers(cls, value: Optional[str]) -> str:
        """Validates that an identifier is a non-empty string.

        Args:
            value (Optional[str]): Raw identifier value.

        Returns:
            str: The identifier.

        Raises:
            MTUnplacedRequirementInvalidId: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUnplacedRequirementInvalidId(
                f"Invalid identifier: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` says what the service is.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The name.

        Raises:
            MTUnplacedRequirementInvalidName: If ``value`` is not a non-empty
                string.

        Notes:
            Required, because the whole point of this record is a message
            somebody can read. A nameless entry is a UUID in a failure report.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUnplacedRequirementInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("day", mode="before")
    def validate_day(cls, value: Union[date, str, None]) -> date:
        """Validates that ``day`` is a date.

        Args:
            value (Union[date, str, None]): Raw ``day`` value.

        Returns:
            date: The day.

        Raises:
            MTUnplacedRequirementInvalidDay: If ``value`` is not a date or an
                ISO-8601 date string.
        """
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise MTUnplacedRequirementInvalidDay(
                    f"Invalid day: {value!r}. Must be an ISO-8601 date."
                ) from None
        raise MTUnplacedRequirementInvalidDay(
            f"Invalid day: {value!r}. Must be a date."
        )

    @field_validator("reason", mode="before")
    def validate_reason(cls, value: Union[str, UnplacedReason, None]) -> UnplacedReason:
        """Validates that ``reason`` is a known reason.

        Args:
            value (Union[str, UnplacedReason, None]): Raw ``reason`` value.

        Returns:
            UnplacedReason: The coerced reason.

        Raises:
            MTUnplacedRequirementInvalidReason: If ``value`` is not a known
                reason.
        """
        if isinstance(value, UnplacedReason):
            return value
        try:
            return UnplacedReason(value)
        except ValueError:
            raise MTUnplacedRequirementInvalidReason(
                f"Invalid reason: {value!r}. Must be one of: "
                f"{', '.join(UnplacedReason.values())}."
            ) from None

    @field_validator("detail", mode="before")
    def validate_detail(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``detail``, when given, is text.

        Args:
            value (Optional[str]): Raw ``detail`` value.

        Returns:
            Optional[str]: The detail, or ``None``.

        Raises:
            MTUnplacedRequirementInvalidDetail: If ``value`` is neither
                ``None`` nor a string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTUnplacedRequirementInvalidDetail(
                f"Invalid detail: {value!r}. Must be a string."
            )
        return value.strip() if value.strip() else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def describe(self) -> str:
        """Return a one-line explanation a planner can act on.

        Returns:
            str: The service, its day, and why it did not fit.
        """
        detail = f" ({self.detail})" if self.detail else ""
        return f"{self.name} on {self.day} — {self.reason.value}{detail}"
