from __future__ import annotations

# Standard library imports
from datetime import date
from typing import List

# Third-party imports
import pytest

# First-party imports
from models.enums import UnplacedReason
from models.planning.planning_run.exceptions import (
    MTUnplacedQuoteInvalidCustomer,
    MTUnplacedQuoteInvalidReference,
    MTUnplacedQuoteInvalidVisits,
)
from models.planning.planning_run.unplaced_quote import UnplacedQuote
from models.planning.planning_run.unplaced_requirement import UnplacedRequirement
from tests.annotations import ModelInput

MONDAY = date(2026, 8, 3)


def _visit(
    requirement_id: str = "req-1",
    reason: UnplacedReason = UnplacedReason.OUT_OF_RADIUS,
) -> UnplacedRequirement:
    """Build one unplaced visit.

    Args:
        requirement_id (str): The identifier to assign.
        reason (UnplacedReason): Why it could not be placed.

    Returns:
        UnplacedRequirement: The diagnosed visit.
    """
    return UnplacedRequirement(
        requirement_id=requirement_id,
        name="Aide a la toilette",
        customer_id="customer-1",
        customer_name="Marie Durand",
        quote_reference="DEV-2026-0042",
        day=MONDAY,
        reason=reason,
    )


class TestBuildingAnUnplacedQuote:
    """Tests for the report entry an operator reads."""

    def test_it_carries_the_quote_the_customer_and_the_visits(self) -> None:
        """The three things somebody needs to act on."""
        entry = UnplacedQuote(
            quote_reference="DEV-2026-0042",
            customer_id="customer-1",
            customer_name="Marie Durand",
            visits=[_visit()],
        )

        assert entry.quote_reference == "DEV-2026-0042"
        assert entry.customer_name == "Marie Durand"
        assert len(entry.visits) == 1

    def test_the_reference_is_trimmed(self) -> None:
        """Whitespace around a reference is not part of it."""
        entry = UnplacedQuote(quote_reference="  DEV-2026-0042  ", visits=[_visit()])

        assert entry.quote_reference == "DEV-2026-0042"

    def test_a_customer_who_could_not_be_loaded_is_tolerated(self) -> None:
        """A missing name must not lose the finding.

        Notes:
            The reference is refused when empty and the name is not, and the
            asymmetry is deliberate: a quote with no readable heading cannot
            be grouped, but a quote whose customer record failed to load is
            still a quote somebody has to look at.
        """
        entry = UnplacedQuote(quote_reference="DEV-2026-0042", visits=[_visit()])

        assert entry.customer_name == ""
        assert entry.visits


class TestRefusingAnUnusableReport:
    """Tests for the values that would make the report meaningless."""

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_a_missing_reference_is_refused(self, value: ModelInput) -> None:
        """A blank heading collapses every quote into one anonymous bucket.

        Args:
            value (ModelInput): The rejected reference.
        """
        with pytest.raises(MTUnplacedQuoteInvalidReference):
            UnplacedQuote(quote_reference=value, visits=[_visit()])

    @pytest.mark.parametrize("value", [42, ["Marie"], {"name": "Marie"}])
    def test_a_customer_name_that_is_not_text_is_refused(
        self, value: ModelInput
    ) -> None:
        """Tolerating a missing name is not tolerating any value at all.

        Args:
            value (ModelInput): The rejected customer name.
        """
        with pytest.raises(MTUnplacedQuoteInvalidCustomer):
            UnplacedQuote(
                quote_reference="DEV-2026-0042",
                customer_name=value,
                visits=[_visit()],
            )

    def test_a_quote_with_nothing_unplaced_is_refused(self) -> None:
        """A report about unplaced work must not list working quotes."""
        with pytest.raises(MTUnplacedQuoteInvalidVisits):
            UnplacedQuote(quote_reference="DEV-2026-0042", visits=[])


class TestSummarisingTheObstacles:
    """Tests for what the entry says about why."""

    def test_repeated_reasons_are_reported_once(self) -> None:
        """Three visits blocked by one cause are one problem.

        Notes:
            Repeating the reason per visit is what made the old message
            unreadable at ninety visits.
        """
        entry = UnplacedQuote(
            quote_reference="DEV-2026-0042",
            visits=[_visit("req-1"), _visit("req-2"), _visit("req-3")],
        )

        assert entry.reasons() == [UnplacedReason.OUT_OF_RADIUS]

    def test_distinct_reasons_are_all_reported(self) -> None:
        """Two different obstacles are two different things to fix."""
        entry = UnplacedQuote(
            quote_reference="DEV-2026-0042",
            visits=[
                _visit("req-1", UnplacedReason.MISSING_CERTIFICATION),
                _visit("req-2", UnplacedReason.OUT_OF_RADIUS),
            ],
        )

        assert entry.reasons() == [
            UnplacedReason.MISSING_CERTIFICATION,
            UnplacedReason.OUT_OF_RADIUS,
        ]

    def test_the_reasons_keep_the_order_they_were_diagnosed_in(self) -> None:
        """First seen, not sorted.

        Notes:
            ``explain_unplaced`` already orders its findings from most to
            least actionable. Re-sorting here would put "no feasible slot"
            above "nobody holds this qualification", which is the opposite of
            what a manager should read first.
        """
        entry = UnplacedQuote(
            quote_reference="DEV-2026-0042",
            visits=[
                _visit("req-1", UnplacedReason.NO_FEASIBLE_SLOT),
                _visit("req-2", UnplacedReason.MISSING_SKILL),
            ],
        )

        assert entry.reasons()[0] is UnplacedReason.NO_FEASIBLE_SLOT

    def test_it_is_frozen(self) -> None:
        """A report is a record of what happened, not a working value."""
        entry = UnplacedQuote(quote_reference="DEV-2026-0042", visits=[_visit()])

        with pytest.raises(Exception):
            entry.quote_reference = "DEV-2026-0043"


class TestRoundTrippingTheReport:
    """Tests that the entry survives storage.

    Notes:
        It is persisted as JSON on the planning run, so a field that cannot
        serialise would fail at the end of a solve — after the expensive part,
        and only for the runs that had something to report.
    """

    def test_it_serialises_and_reloads_unchanged(self) -> None:
        """What goes into the column comes back out of it."""
        entry = UnplacedQuote(
            quote_reference="DEV-2026-0042",
            customer_id="customer-1",
            customer_name="Marie Durand",
            visits=[_visit("req-1"), _visit("req-2")],
        )

        restored = UnplacedQuote.model_validate(entry.model_dump(mode="json"))

        assert restored == entry

    def test_every_visit_keeps_its_reason_through_storage(self) -> None:
        """The reason is the part an operator acts on."""
        visits: List[UnplacedRequirement] = [
            _visit("req-1", UnplacedReason.MISSING_CERTIFICATION)
        ]
        entry = UnplacedQuote(quote_reference="DEV-2026-0042", visits=visits)

        restored = UnplacedQuote.model_validate(entry.model_dump(mode="json"))

        assert restored.visits[0].reason is UnplacedReason.MISSING_CERTIFICATION
