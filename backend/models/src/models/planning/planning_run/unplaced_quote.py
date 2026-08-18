from __future__ import annotations

# Standard library imports
from typing import List, Union

# Third-party imports
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First-party imports
from models.enums import UnplacedReason
from models.planning.planning_run.exceptions.unplaced_quote_exceptions import (
    MTUnplacedQuoteInvalidCustomer,
    MTUnplacedQuoteInvalidReference,
    MTUnplacedQuoteInvalidVisits,
)
from models.planning.planning_run.suggested_slot import SuggestedSlot
from models.planning.planning_run.unplaced_requirement import (
    UnplacedRequirement,  # noqa: E501
)


class UnplacedQuote(BaseModel):
    """Everything one quote could not fit into a week, as an operator sees it.

    Attributes:
        quote_reference (str): The quote, as printed on the document.
        customer_id (str): Whose work it is.
        customer_name (str): The same person, by name.
        visits (List[UnplacedRequirement]): The visits that were not placed,
            each with its own reason.
        alternatives (List[SuggestedSlot]): Times somebody qualified is free,
            offered so the person renegotiating has something to propose
            rather than only a problem to report. Empty when nothing was
            found, which is itself an answer: the week is full.

    Notes:
        - **The report is grouped by quote because that is the unit somebody can
          act on.** A list of thirty unplaced visits tells an operator that
          something is wrong; "quote DEV-2026-0042 for Marie Durand, three
          visits, nobody holds DEAES" tells them who to telephone and what to
          say. The visit is what the solver failed on, but the quote is what the
          agency sold, and it is the quote that has to be renegotiated,
          rescheduled or staffed.
        - No sentence is built here. The screen assembles one from these fields
          in the reader's own language. A message composed in the backend would
          arrive in French for an English operator, and the quote emails already
          taught this codebase that lesson once.
    """

    model_config = ConfigDict(frozen=True)

    quote_reference: str = Field(description="The quote, as printed on it.")
    customer_id: str = Field(default="", description="Whose work it is.")
    customer_name: str = Field(default="", description="Whose work it is, by name.")
    visits: List[UnplacedRequirement] = Field(
        description="The visits from this quote that were not placed."
    )
    alternatives: List[SuggestedSlot] = Field(
        default_factory=list,
        description="Times somebody qualified is free, offered instead.",
    )

    ############################
    #    Validation Methods    #
    ############################

    @field_validator("quote_reference", mode="before")
    def validate_quote_reference(cls, value: Union[str, None]) -> str:
        """Validates that the quote reference is readable text.

        Args:
            value (Union[str, None]): Raw reference.

        Returns:
            str: The trimmed reference.

        Raises:
            MTUnplacedQuoteInvalidReference: If it is not a non-empty string.

        Notes:
            Empty is refused rather than tolerated. A report grouped under a
            blank heading is a report an operator cannot act on, and the
            grouping is the whole point of this model — silently accepting a
            missing reference would produce exactly one anonymous bucket
            holding every quote's problems at once.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUnplacedQuoteInvalidReference(
                f"Invalid quote_reference: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("customer_name", "customer_id", mode="before")
    def validate_customer(cls, value: Union[str, None]) -> str:
        """Validates that a customer field is text, defaulting to empty.

        Args:
            value (Union[str, None]): Raw value.

        Returns:
            str: The trimmed value, or an empty string.

        Raises:
            MTUnplacedQuoteInvalidCustomer: If the value is not text.

        Notes:
            Missing is allowed where the reference is not. A customer whose
            record could not be loaded still has a quote to report against,
            and refusing the whole report over an unresolvable name would lose
            the finding entirely.
        """
        if value is None:
            return ""
        if not isinstance(value, str):
            raise MTUnplacedQuoteInvalidCustomer(
                f"Invalid customer field: {value!r}. Must be a string."
            )
        return value.strip()

    @field_validator("visits")
    def validate_visits(
        cls, value: List[UnplacedRequirement]
    ) -> List[UnplacedRequirement]:
        """Validates that the quote has something to report.

        Args:
            value (List[UnplacedRequirement]): The unplaced visits.

        Returns:
            List[UnplacedRequirement]: The same list.

        Raises:
            MTUnplacedQuoteInvalidVisits: If the list is empty.

        Notes:
            A quote with nothing unplaced does not belong in a report about
            unplaced work. Allowing it would put quotes on the screen that are
            perfectly fine, which is worse than saying nothing.
        """
        if not value:
            raise MTUnplacedQuoteInvalidVisits(
                "Invalid visits: a quote with no unplaced visit is not a finding."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def reasons(self) -> List[UnplacedReason]:
        """Return the distinct obstacles, most actionable first.

        Returns:
            List[UnplacedReason]: The reasons, without repetition.

        Notes:
            Three visits blocked by the same missing qualification are one
            problem, not three. Repeating the reason per visit is what made
            the old message unreadable at ninety visits.
        """
        seen: List[UnplacedReason] = []
        for visit in self.visits:
            if visit.reason not in seen:
                seen.append(visit.reason)
        return seen
