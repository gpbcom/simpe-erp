from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List, Optional, Union

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
from models.planning.planning_run.suggested_slot import SuggestedSlot


class UnplacedRequirement(BaseModel):
    """A piece of accepted work the planner could not schedule, and why.

    Attributes:
        requirement_id (str): The work that could not be placed.
        name (str): What the service is, for a message a planner can act on.
        customer_id (str): Whose work it is.
        customer_name (str): The same person, by name. An identifier is
            unreadable on a screen and unsearchable in an inbox.
        quote_reference (str): The quote the work was sold on. This is what an
            operator has in front of them when a customer telephones, so it is
            what the report is grouped by.
        day (date): The day it had to happen on.
        reason (UnplacedReason): Why it could not be placed.
        detail (Optional[str]): The specifics — the distance measured, the
            visit it clashes with.
        quote_line_id (Optional[str]): The quote line this work was sold on,
            so an operator accepting one of the offered slots moves the right
            line.
        alternatives (List[SuggestedSlot]): Times somebody qualified is free,
            offered instead of *this* visit's.

    Notes:
        - This exists so that a failed planning run says *what to change* rather
          than "infeasible". "No assistant lives within 30 km of Mme Durand" is a
          sentence a manager can act on by widening the radius or hiring;
          "INFEASIBLE" is not.
        - Carries the name and the customer, not just an identifier, because the
          message is read by somebody who knows their customers by name and has
          never seen a UUID.
        - **The offers belong to the visit, not to the quote.** A quote with two
          unplaced visits has two sets of free times, and one flat list gives an
          operator no way to tell which slot answers which problem — nor a screen
          any way to make them clickable without guessing.
        - ``quote_line_id`` and ``alternatives`` both default, and that is
          load-bearing rather than lax: this record is stored as JSON on the
          quote and re-validated on every read, so a row written before these
          fields existed has to keep loading. A required field here would take
          the quotes list down for every quote a planner has ever returned.
    """

    requirement_id: str = Field(description="The work that could not be placed.")
    name: str = Field(description="What the service is.")
    customer_id: str = Field(description="Whose work it is.")
    customer_name: str = Field(
        default="",
        description="Whose work it is, by name rather than by identifier.",
    )
    quote_reference: str = Field(
        default="",
        description="The quote it was sold on, as printed on the document.",
    )
    day: date = Field(description="The day it had to happen on.")
    reason: UnplacedReason = Field(description="Why it could not be placed.")
    detail: Optional[str] = Field(
        default=None, description="The specifics behind the reason."
    )
    quote_line_id: Optional[str] = Field(
        default=None,
        description="The quote line this work was sold on.",
    )
    alternatives: List[SuggestedSlot] = Field(
        default_factory=list,
        description="Times somebody qualified is free instead of this visit's.",
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
    def validate_day(cls, value: Optional[Union[date, str]]) -> date:
        """Validates that ``day`` is a date.

        Args:
            value (Optional[Union[date, str]]): Raw ``day`` value.

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
    def validate_reason(
        cls, value: Optional[Union[str, UnplacedReason]]
    ) -> UnplacedReason:  # noqa: E501
        """Validates that ``reason`` is a known reason.

        Args:
            value (Optional[Union[str, UnplacedReason]]): Raw ``reason`` value.

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

    @field_validator("quote_line_id", mode="before")
    def validate_quote_line_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``quote_line_id``, when given, identifies a line.

        Args:
            value (Optional[str]): Raw ``quote_line_id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` when absent.

        Raises:
            MTUnplacedRequirementInvalidId: If ``value`` is neither ``None``
                nor a non-empty string.

        Notes:
            Blank becomes ``None`` rather than an empty string. A screen decides
            whether to offer the slots by asking whether there is a line to move,
            and ``""`` would answer yes to a question it cannot act on.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTUnplacedRequirementInvalidId(
                f"Invalid quote_line_id: {value!r}. Must be a string or None."
            )
        return value.strip() or None

    ############################
    # Publicly Exposed Methods #
    ############################

    def describe(self) -> str:
        """Return a one-line explanation a planner can act on.

        Returns:
            str: The service, its day, and why it did not fit.

        Notes:
            Kept as the terse form for logs. What an operator reads on screen
            is assembled from the structured fields instead — a sentence built
            here could not be translated, and this application ships in two
            languages.
        """
        detail = f" ({self.detail})" if self.detail else ""
        return f"{self.name} on {self.day} — {self.reason.value}{detail}"
