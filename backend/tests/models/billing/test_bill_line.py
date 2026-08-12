from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.billing.bill_line import BillLine
from models.billing.exceptions import (
    MTBillLineInvalidAmount,
    MTBillLineInvalidDuration,
    MTBillLineInvalidHca,
    MTBillLineInvalidId,
    MTBillLineInvalidName,
    MTBillLineInvalidServiceCategory,
    MTBillLineInvalidServiceDate,
    MTBillLineInvalidVatRate,
    MTBillLineInvalidVisit,
    MTBillLineInvalidWindow,
)
from models.enums import ServiceCategory
from tests.annotations import ModelInput


def a_line(**overrides: ModelInput) -> Dict[str, ModelInput]:
    """Build the payload of a delivered, priced charge.

    Args:
        **overrides: Fields to replace on the default payload.

    Returns:
        Dict[str, ModelInput]: A payload ``BillLine`` accepts.
    """
    payload: Dict[str, ModelInput] = {
        "quote_line_id": "quote-line-1",
        "intervention_id": "intervention-1",
        "name": "Aide à la toilette",
        "service_category": ServiceCategory.NECESSITY,
        "service_date": date(2026, 3, 9),
        "day": date(2026, 3, 9),
        "start_time": time(9, 0),
        "end_time": time(11, 0),
        "hca_full_name": "Amina Benali",
        "duration_minutes": 120,
        "hourly_rate_ht": Decimal("31.91"),
        "total_ht": Decimal("63.82"),
        "vat_rate": Decimal("0.055"),
        "vat_amount": Decimal("3.51"),
        "total_ttc": Decimal("67.33"),
    }
    payload.update(overrides)
    return payload


class TestBillLineIdentity:
    """Tests for what a charge says about where it came from."""

    def test_a_charge_names_the_quote_line_it_came_from(self) -> None:
        """Provenance is required, so a disputed charge can be traced."""
        assert BillLine(**a_line()).quote_line_id == "quote-line-1"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_a_charge_without_an_origin_is_refused(self, value: ModelInput) -> None:
        """Every charge comes from something that was sold."""
        with pytest.raises(MTBillLineInvalidId):
            BillLine(**a_line(quote_line_id=value))

    def test_the_intervention_is_optional(self) -> None:
        """A service the planner never placed is still billable.

        Notes:
            Refusing it would silently forgive work the agency delivered off
            the plan, which is money the agency simply never asks for.
        """
        line = BillLine(
            **a_line(intervention_id=None, day=None, start_time=None, end_time=None)
        )
        assert line.was_delivered() is False

    def test_identifiers_are_stripped(self) -> None:
        """Surrounding whitespace never distinguishes two identifiers."""
        assert BillLine(**a_line(quote_line_id="  ql-1  ")).quote_line_id == "ql-1"


class TestBillLineDescription:
    """Tests for the designation column of the invoice."""

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - whitespace"),
        ],
    )
    def test_a_charge_must_describe_itself(self, value: ModelInput) -> None:
        """French law requires the service rendered to be described.

        Notes:
            An empty designation prints a row of figures against nothing, which
            is a defect on the document rather than an inconvenience.
        """
        with pytest.raises(MTBillLineInvalidName):
            BillLine(**a_line(name=value))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("weekly", id="Invalid - not a category"),
        ],
    )
    def test_the_vat_category_has_no_default(self, value: ModelInput) -> None:
        """Guessing the category would misstate the tax on the invoice."""
        with pytest.raises(MTBillLineInvalidServiceCategory):
            BillLine(**a_line(service_category=value))

    def test_the_assistant_may_be_unknown_but_never_blank(self) -> None:
        """A named assistant is optional; a blank one is a lost value."""
        assert BillLine(**a_line(hca_full_name=None)).hca_full_name is None
        with pytest.raises(MTBillLineInvalidHca):
            BillLine(**a_line(hca_full_name="   "))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - None"),
            pytest.param(12345, id="Invalid - int"),
            pytest.param(object(), id="Invalid - object"),
        ],
    )
    def test_the_sold_day_must_be_a_date(self, value: ModelInput) -> None:
        """The service date decides which period the charge belongs to."""
        with pytest.raises(MTBillLineInvalidServiceDate):
            BillLine(**a_line(service_date=value))


class TestBillLineVisit:
    """Tests for the delivered visit recorded against a charge."""

    def test_a_delivered_visit_is_recorded_whole(self) -> None:
        """The day, the start and the end travel together."""
        line = BillLine(**a_line())
        assert line.was_delivered() is True
        assert (line.day, line.start_time, line.end_time) == (
            date(2026, 3, 9),
            time(9, 0),
            time(11, 0),
        )

    @pytest.mark.parametrize(
        "missing",
        [
            pytest.param({"day": None}, id="Invalid - no day"),
            pytest.param({"start_time": None}, id="Invalid - no start"),
            pytest.param({"end_time": None}, id="Invalid - no end"),
        ],
    )
    def test_half_a_visit_is_refused(self, missing: Dict[str, ModelInput]) -> None:
        """A partial visit leaves the reader unable to say what happened.

        Notes:
            A date with no hours beside it looks the same as a service the
            planner never placed, and the two mean different things to whoever
            answers the customer's telephone call.
        """
        with pytest.raises(MTBillLineInvalidVisit):
            BillLine(**a_line(**missing))

    def test_a_charge_with_no_visit_at_all_is_accepted(self) -> None:
        """None of the three set is the unplanned case, not a broken one."""
        line = BillLine(
            **a_line(day=None, start_time=None, end_time=None, intervention_id=None)
        )
        assert line.was_delivered() is False

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            pytest.param(time(11, 0), time(9, 0), id="Invalid - reversed"),
            pytest.param(time(9, 0), time(9, 0), id="Invalid - zero length"),
        ],
    )
    def test_a_visit_must_run_forwards(self, start: time, end: time) -> None:
        """A visit occupying no time was not a visit."""
        with pytest.raises(MTBillLineInvalidWindow):
            BillLine(**a_line(start_time=start, end_time=end))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(900, id="Invalid - int"),
            pytest.param(object(), id="Invalid - object"),
        ],
    )
    def test_a_clock_time_must_be_a_time(self, value: ModelInput) -> None:
        """Only a time or an ISO string names an hour of the day."""
        with pytest.raises(MTBillLineInvalidWindow):
            BillLine(**a_line(start_time=value))


class TestBillLineDuration:
    """Tests for the quantity column of the invoice."""

    def test_duration_hours_is_exact(self) -> None:
        """Fifty minutes is not representable as a float fraction of an hour.

        Notes:
            The quantity is multiplied by a rate, so an approximation here
            reaches the invoice as a cent nobody can account for.
        """
        line = BillLine(**a_line(duration_minutes=50))
        assert line.duration_hours() == Decimal(50) / Decimal(60)
        assert isinstance(line.duration_hours(), Decimal)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-30, id="Invalid - negative"),
            pytest.param(24 * 60 + 1, id="Invalid - longer than a day"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param("120", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_unusable_duration_is_refused(self, value: ModelInput) -> None:
        """An amount charged for no time is an invoice nobody pays."""
        with pytest.raises(MTBillLineInvalidDuration):
            BillLine(**a_line(duration_minutes=value))


class TestBillLineMoney:
    """Tests for the amounts, which unlike a quote line's are mandatory."""

    @pytest.mark.parametrize("field", list(BillLine.MONEY_FIELDS))
    def test_every_amount_is_required(self, field: str) -> None:
        """A bill line has no unpriced state.

        Notes:
            **The one place this differs from a quote line.** A quote is
            legitimately unpriced while it is being composed; an invoice with a
            blank amount column is a legal defect, so the model refuses to exist
            rather than print one.
        """
        with pytest.raises(MTBillLineInvalidAmount):
            BillLine(**a_line(**{field: None}))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(Decimal("-1"), id="Invalid - negative"),
            pytest.param("not a number", id="Invalid - unparseable"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param(float("inf"), id="Invalid - infinite"),
        ],
    )
    def test_an_unusable_amount_is_refused(self, value: ModelInput) -> None:
        """Only a finite, non-negative decimal is money."""
        with pytest.raises(MTBillLineInvalidAmount):
            BillLine(**a_line(total_ht=value))

    def test_a_float_keeps_its_exact_value(self) -> None:
        """Money is routed through ``str`` so binary rounding never enters.

        Notes:
            ``Decimal(63.82)`` is 63.81999... and would print a cent short over
            enough lines; ``Decimal(str(63.82))`` is exactly 63.82.
        """
        assert BillLine(**a_line(total_ht=63.82)).total_ht == Decimal("63.82")

    def test_the_vat_rate_is_stored_not_derived(self) -> None:
        """The rate charged is a fact about a past transaction.

        Notes:
            Derived from the category, a reprint after a statutory change would
            quietly restate every historic invoice at the new rate.
        """
        line = BillLine(
            **a_line(
                service_category=ServiceCategory.NECESSITY,
                vat_rate=Decimal("0.20"),
            )
        )
        assert line.vat_rate == Decimal("0.20")
        assert line.service_category.vat_rate() == Decimal("0.055")

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param(Decimal("-0.01"), id="Invalid - negative"),
            pytest.param(Decimal("5.5"), id="Invalid - a percentage"),
            pytest.param("not a rate", id="Invalid - unparseable"),
        ],
    )
    def test_an_unusable_vat_rate_is_refused(self, value: ModelInput) -> None:
        """A rate is a proportion, never a percentage.

        Notes:
            ``5.5`` and ``0.055`` look alike in a stored row and differ by a
            factor of a hundred on the page, so the range check is what makes
            the unit unambiguous.
        """
        with pytest.raises(MTBillLineInvalidVatRate):
            BillLine(**a_line(vat_rate=value))
