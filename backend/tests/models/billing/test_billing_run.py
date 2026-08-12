from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.billing.billing_run import BillingRun
from models.billing.exceptions import (
    MTBillingRunInvalidDate,
    MTBillingRunInvalidError,
    MTBillingRunInvalidId,
    MTBillingRunInvalidIdentifiers,
    MTBillingRunInvalidMoment,
    MTBillingRunInvalidPeriod,
    MTBillingRunInvalidPeriodicity,
    MTBillingRunInvalidStatus,
)
from models.enums import BillingPeriodicity, BillingRunStatus
from tests.annotations import ModelInput


def a_run(**overrides: ModelInput) -> Dict[str, ModelInput]:
    """Build the payload of a request to bill March.

    Args:
        **overrides: Fields to replace on the default payload.

    Returns:
        Dict[str, ModelInput]: A payload ``BillingRun`` accepts.
    """
    payload: Dict[str, ModelInput] = {
        "company_id": "company-1",
        "requested_by": "user-1",
        "reference_date": date(2026, 4, 1),
        "periodicity": BillingPeriodicity.MONTHLY,
        "period_start": date(2026, 3, 1),
        "period_end": date(2026, 3, 31),
    }
    payload.update(overrides)
    return payload


class TestBillingRunIdentity:
    """Tests for what a run says about who asked for it."""

    def test_a_run_starts_queued(self) -> None:
        """The record exists before the work does."""
        assert BillingRun(**a_run()).status is BillingRunStatus.PENDING

    def test_the_agency_is_required(self) -> None:
        """A run that named no agency would bill everybody's customers.

        Notes:
            Required with no default for the reason the event publisher requires
            one: a forgotten argument must fail at the call site rather than
            become a silently wider job.
        """
        with pytest.raises(MTBillingRunInvalidId):
            BillingRun(**a_run(company_id=None))

    def test_the_requester_is_optional_but_never_blank(self) -> None:
        """A run may be triggered by a schedule; a blank actor is a lost one."""
        assert BillingRun(**a_run(requested_by=None)).requested_by is None
        with pytest.raises(MTBillingRunInvalidId):
            BillingRun(**a_run(requested_by="  "))

    def test_an_unknown_status_is_refused(self) -> None:
        """Only the five statuses the lifecycle defines are storable."""
        with pytest.raises(MTBillingRunInvalidStatus):
            BillingRun(**a_run(status="cancelled"))

    def test_an_unknown_periodicity_is_refused(self) -> None:
        """The window came from a rule, and the rule has to be a known one."""
        with pytest.raises(MTBillingRunInvalidPeriodicity):
            BillingRun(**a_run(periodicity="fortnightly"))


class TestBillingRunPeriod:
    """Tests for the window a run bills."""

    def test_the_window_is_stored_not_recomputed(self) -> None:
        """An agency that changes its periodicity must not rewrite history.

        Notes:
            Recomputed from the reference date on read, a run would afterwards
            claim to have billed a period it never touched.
        """
        run = BillingRun(**a_run())
        assert (run.period_start, run.period_end) == (
            date(2026, 3, 1),
            date(2026, 3, 31),
        )

    def test_a_reversed_window_is_refused(self) -> None:
        """A period ending before it starts bills nothing."""
        with pytest.raises(MTBillingRunInvalidPeriod):
            BillingRun(**a_run(period_end=date(2026, 2, 1)))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param(20260401, id="Invalid - int"),
        ],
    )
    def test_a_date_field_must_be_a_date(self, value: ModelInput) -> None:
        """Only a date names a day."""
        with pytest.raises(MTBillingRunInvalidDate):
            BillingRun(**a_run(reference_date=value))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(20260401, id="Invalid - int"),
            pytest.param(object(), id="Invalid - object"),
        ],
    )
    def test_a_timestamp_must_be_a_moment(self, value: ModelInput) -> None:
        """Only a datetime or an ISO string records when something happened."""
        with pytest.raises(MTBillingRunInvalidMoment):
            BillingRun(**a_run(started_at=value))


class TestBillingRunOutcome:
    """Tests for what a run records about what it managed to do."""

    def test_both_outcome_lists_are_kept(self) -> None:
        """A partial month is only actionable if it names who went unbilled.

        Notes:
            A count would leave somebody comparing two lists by hand to find the
            customers whose invoices were never written.
        """
        run = BillingRun(
            **a_run(
                status=BillingRunStatus.PARTIAL,
                bill_ids=["bill-1", "bill-2"],
                failed_customer_ids=["customer-9"],
            )
        )
        assert run.bill_count() == 2
        assert run.failure_count() == 1

    def test_a_repeated_identifier_is_recorded_once(self) -> None:
        """A retry must not make the run look as though it billed twice."""
        run = BillingRun(**a_run(bill_ids=["bill-1", "bill-1", "bill-2"]))
        assert run.bill_ids == ["bill-1", "bill-2"]

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("bill-1", id="Invalid - a bare string"),
            pytest.param([""], id="Invalid - an empty identifier"),
            pytest.param([7], id="Invalid - a number"),
        ],
    )
    def test_an_unusable_outcome_list_is_refused(self, value: ModelInput) -> None:
        """The lists are what a partial run is read from."""
        with pytest.raises(MTBillingRunInvalidIdentifiers):
            BillingRun(**a_run(bill_ids=value))

    def test_an_absent_outcome_list_reads_as_empty(self) -> None:
        """A run that has not started yet has billed nobody."""
        assert BillingRun(**a_run(bill_ids=None)).bill_ids == []

    def test_a_blank_failure_message_is_refused(self) -> None:
        """A failure whose reason renders blank looks like a success.

        Notes:
            On screen the two are indistinguishable, and the run that quietly
            billed nobody is the one somebody needs to look at.
        """
        with pytest.raises(MTBillingRunInvalidError):
            BillingRun(**a_run(error="   "))

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            pytest.param(BillingRunStatus.PENDING, False, id="queued"),
            pytest.param(BillingRunStatus.RUNNING, False, id="running"),
            pytest.param(BillingRunStatus.SUCCEEDED, True, id="succeeded"),
            pytest.param(BillingRunStatus.PARTIAL, True, id="partial"),
            pytest.param(BillingRunStatus.FAILED, True, id="failed"),
        ],
    )
    def test_is_terminal_defers_to_the_status(
        self, status: BillingRunStatus, expected: bool
    ) -> None:
        """A client polling and a worker publishing must agree on "finished".

        Notes:
            Delegated rather than reimplemented, so the rule cannot be stated
            twice and drift.
        """
        assert BillingRun(**a_run(status=status)).is_terminal() is expected
