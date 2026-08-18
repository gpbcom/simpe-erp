from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import Tuple

# Third-party imports
import pytest

# First-party imports
from models.enums import BillingPeriodicity, BillingRunStatus, BillStatus
from models.exceptions.enum_exceptions import MTInvalidBillingPeriodicity
from tests.annotations import ModelInput


class TestBillingPeriodicity:
    """Tests for the window a periodicity resolves a day into.

    Notes:
        These are the whole of requirement 3. A quote line carries one
        ``service_date``, so "only the part inside the window is billed" is a
        date filter and nothing else — which makes the window's two bounds the
        only thing that can get the pro-rata wrong, and makes their edges worth
        pinning one by one.
    """

    ############################
    # Weekly                   #
    ############################

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            pytest.param(
                date(2026, 8, 13),
                (date(2026, 8, 10), date(2026, 8, 16)),
                id="a Thursday resolves to its Monday and Sunday",
            ),
            pytest.param(
                date(2026, 8, 10),
                (date(2026, 8, 10), date(2026, 8, 16)),
                id="the Monday itself is the start",
            ),
            pytest.param(
                date(2026, 8, 16),
                (date(2026, 8, 10), date(2026, 8, 16)),
                id="the Sunday itself is the end",
            ),
            pytest.param(
                date(2026, 1, 1),
                (date(2025, 12, 29), date(2026, 1, 4)),
                id="a week straddling new year keeps its Monday",
            ),
        ],
    )
    def test_weekly_window(self, day: date, expected: Tuple[date, date]) -> None:
        """A weekly window runs Monday to Sunday around the given day.

        Notes:
            The Monday and Sunday cases matter more than the midweek one: an
            off-by-one at either bound would bill a visit twice, once at the end
            of a week and again at the start of the next.
        """
        assert BillingPeriodicity.WEEKLY.window(day) == expected

    ############################
    # Monthly                  #
    ############################

    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            pytest.param(
                date(2026, 1, 15),
                (date(2026, 1, 1), date(2026, 1, 31)),
                id="a 31-day month",
            ),
            pytest.param(
                date(2026, 4, 7),
                (date(2026, 4, 1), date(2026, 4, 30)),
                id="a 30-day month",
            ),
            pytest.param(
                date(2026, 2, 10),
                (date(2026, 2, 1), date(2026, 2, 28)),
                id="a common February",
            ),
            pytest.param(
                date(2024, 2, 10),
                (date(2024, 2, 1), date(2024, 2, 29)),
                id="a leap February",
            ),
            pytest.param(
                date(2026, 12, 3),
                (date(2026, 12, 1), date(2026, 12, 31)),
                id="December rolls the year over",
            ),
        ],
    )
    def test_monthly_window(self, day: date, expected: Tuple[date, date]) -> None:
        """A monthly window is the whole calendar month.

        Notes:
            December is here because the last day is computed as "the first of
            next month, minus one day", and that is the one month whose next
            month is in another year.
        """
        assert BillingPeriodicity.MONTHLY.window(day) == expected

    ############################
    # Yearly                   #
    ############################

    @pytest.mark.parametrize(
        "day",
        [
            pytest.param(date(2026, 1, 1), id="the first day"),
            pytest.param(date(2026, 7, 7), id="a midyear day"),
            pytest.param(date(2026, 12, 31), id="the last day"),
        ],
    )
    def test_yearly_window(self, day: date) -> None:
        """A yearly window is 1 January to 31 December inclusive."""
        assert BillingPeriodicity.YEARLY.window(day) == (
            date(2026, 1, 1),
            date(2026, 12, 31),
        )

    ############################
    # The inclusive end bound  #
    ############################

    @pytest.mark.parametrize("periodicity", list(BillingPeriodicity))
    def test_the_window_contains_both_of_its_bounds(
        self, periodicity: BillingPeriodicity
    ) -> None:
        """Both bounds belong to the period they delimit.

        Notes:
            Stated as its own test because it is the property the whole feature
            rests on. An exclusive end would be the one period in this
            application that behaved differently from
            ``QuoteRepository.list_schedulable`` and ``Quote.covers``, and the
            symptom would be a day's care silently unbilled every period.
        """
        start, end = periodicity.window(date(2026, 5, 20))
        assert start <= end
        assert periodicity.window(start) == (start, end)
        assert periodicity.window(end) == (start, end)

    ############################
    # Previous window          #
    ############################

    @pytest.mark.parametrize(
        ("periodicity", "day", "expected"),
        [
            pytest.param(
                BillingPeriodicity.WEEKLY,
                date(2026, 8, 13),
                (date(2026, 8, 3), date(2026, 8, 9)),
                id="the week before",
            ),
            pytest.param(
                BillingPeriodicity.MONTHLY,
                date(2026, 1, 15),
                (date(2025, 12, 1), date(2025, 12, 31)),
                id="January's predecessor is last December",
            ),
            pytest.param(
                BillingPeriodicity.MONTHLY,
                date(2026, 3, 31),
                (date(2026, 2, 1), date(2026, 2, 28)),
                id="31 March lands on the whole of February",
            ),
            pytest.param(
                BillingPeriodicity.YEARLY,
                date(2026, 7, 7),
                (date(2025, 1, 1), date(2025, 12, 31)),
                id="the year before",
            ),
        ],
    )
    def test_previous_window(
        self,
        periodicity: BillingPeriodicity,
        day: date,
        expected: Tuple[date, date],
    ) -> None:
        """The previous window is the one ending the day before this one starts.

        Notes:
            The 31 March case is the reason this is a method rather than
            arithmetic at each call site: subtracting a month from the *day*
            would land on 28 February and bill three days twice.
        """
        assert periodicity.previous_window(day) == expected

    def test_previous_window_abuts_the_current_one(self) -> None:
        """No day falls between a window and its predecessor."""
        current = BillingPeriodicity.MONTHLY.window(date(2026, 6, 10))
        previous = BillingPeriodicity.MONTHLY.previous_window(date(2026, 6, 10))
        assert (current[0] - previous[1]).days == 1

    ############################
    # Refusals                 #
    ############################

    def test_a_datetime_is_accepted_as_its_day(self) -> None:
        """A moment resolves to the window holding its date."""
        assert BillingPeriodicity.MONTHLY.window(datetime(2026, 3, 9, 14, 30)) == (
            date(2026, 3, 1),
            date(2026, 3, 31),
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("2026-01-15", id="Invalid - ISO string"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(20260115, id="Invalid - int"),
            pytest.param(object(), id="Invalid - arbitrary object"),
        ],
    )
    def test_window_for_refuses_anything_that_is_not_a_date(
        self, value: ModelInput
    ) -> None:
        """Only a date names a period.

        Notes:
            Refused rather than parsed. ``window_for`` decides what a customer
            is charged for, and a string that happened to parse into some other
            day would bill the wrong month with nothing looking wrong.
        """
        with pytest.raises(MTInvalidBillingPeriodicity):
            BillingPeriodicity.MONTHLY.window(value)


class TestBillStatus:
    """Tests for the commercial lifecycle of a bill."""

    def test_the_four_statuses_are_in_lifecycle_order(self) -> None:
        """A bill is validated, then accepted, then awaited, then paid."""
        assert BillStatus.values() == (
            "to-be-validated",
            "accepted",
            "waiting-payment",
            "paid",
        )

    def test_a_new_bill_starts_awaiting_validation(self) -> None:
        """The first member is the one a generation run writes.

        Notes:
            Declaration order is what ``can_move_to`` reads, so the first member
            being the starting state is load-bearing rather than cosmetic.
        """
        assert tuple(BillStatus)[0] is BillStatus.TO_BE_VALIDATED

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            pytest.param(
                BillStatus.TO_BE_VALIDATED,
                BillStatus.ACCEPTED,
                id="validating it",
            ),
            pytest.param(
                BillStatus.ACCEPTED,
                BillStatus.WAITING_PAYMENT,
                id="sending it",
            ),
            pytest.param(
                BillStatus.WAITING_PAYMENT,
                BillStatus.PAID,
                id="settling it",
            ),
        ],
    )
    def test_each_forward_step_is_allowed(
        self, current: BillStatus, target: BillStatus
    ) -> None:
        """The lifecycle runs forward one status at a time."""
        assert current.can_move_to(target) is True

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            pytest.param(
                BillStatus.ACCEPTED,
                BillStatus.TO_BE_VALIDATED,
                id="un-validating it",
            ),
            pytest.param(
                BillStatus.WAITING_PAYMENT,
                BillStatus.ACCEPTED,
                id="un-sending it",
            ),
            pytest.param(
                BillStatus.PAID,
                BillStatus.WAITING_PAYMENT,
                id="un-settling it",
            ),
        ],
    )
    def test_each_step_back_is_allowed(
        self, current: BillStatus, target: BillStatus
    ) -> None:
        """One step back is the correction path.

        Notes:
            A manager who marked the wrong row paid needs this. An irreversible
            status would leave them editing the database by hand, which is worse
            than any ordering it protects.
        """
        assert current.can_move_to(target) is True

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            pytest.param(
                BillStatus.TO_BE_VALIDATED,
                BillStatus.WAITING_PAYMENT,
                id="Invalid - skipping the validation",
            ),
            pytest.param(
                BillStatus.TO_BE_VALIDATED,
                BillStatus.PAID,
                id="Invalid - straight to paid",
            ),
            pytest.param(
                BillStatus.ACCEPTED,
                BillStatus.PAID,
                id="Invalid - skipping the sending",
            ),
            pytest.param(
                BillStatus.PAID,
                BillStatus.TO_BE_VALIDATED,
                id="Invalid - unwinding the whole lifecycle",
            ),
        ],
    )
    def test_a_skip_is_refused(self, current: BillStatus, target: BillStatus) -> None:
        """Nothing may jump more than one status.

        Notes:
            A bill going straight from awaiting validation to paid would skip
            the record of it ever having been approved, and of it ever having
            been sent — the audit trail the four statuses exist to keep.
        """
        assert current.can_move_to(target) is False

    @pytest.mark.parametrize("status", list(BillStatus))
    def test_a_status_cannot_move_to_itself(self, status: BillStatus) -> None:
        """Re-setting the status a bill already holds is not a transition."""
        assert status.can_move_to(status) is False

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            pytest.param(BillStatus.TO_BE_VALIDATED, False, id="awaiting validation"),
            pytest.param(BillStatus.ACCEPTED, False, id="accepted"),
            pytest.param(BillStatus.WAITING_PAYMENT, False, id="awaiting payment"),
            pytest.param(BillStatus.PAID, True, id="paid ends it"),
        ],
    )
    def test_is_terminal(self, status: BillStatus, expected: bool) -> None:
        """Only a paid bill has nothing further to reach."""
        assert status.is_terminal() is expected

    def test_there_is_no_cancelled_status(self) -> None:
        """A mistaken invoice is corrected by a credit note, not withdrawn.

        Notes:
            French invoice numbering forbids both reuse and gaps, so a status
            that took a bill out of the series would break the chronology the
            sequence exists to prove.
        """
        assert "cancelled" not in BillStatus.values()


class TestBillingRunStatus:
    """Tests for the lifecycle of a bill-generation run."""

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            pytest.param(BillingRunStatus.PENDING, False, id="pending is not terminal"),
            pytest.param(BillingRunStatus.RUNNING, False, id="running is not terminal"),
            pytest.param(BillingRunStatus.SUCCEEDED, True, id="succeeded is terminal"),
            pytest.param(BillingRunStatus.PARTIAL, True, id="partial is terminal"),
            pytest.param(BillingRunStatus.FAILED, True, id="failed is terminal"),
        ],
    )
    def test_is_terminal(self, status: BillingRunStatus, expected: bool) -> None:
        """A partial run is finished, so a client must stop polling it.

        Notes:
            The bills that could be written are written. Nothing more will
            happen to the run, and a client that kept polling would wait
            forever.
        """
        assert status.is_terminal() is expected
