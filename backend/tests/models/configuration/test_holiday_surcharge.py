from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.configuration.exceptions import (
    MTHolidaySurchargeInvalidDay,
    MTHolidaySurchargeInvalidLabel,
    MTHolidaySurchargeInvalidMonth,
    MTHolidaySurchargeInvalidSurcharge,
    MTInvalidHolidaySurchargeException,
)
from models.configuration.holiday_surcharge import HolidaySurcharge


@pytest.fixture
def valid_holiday_kwargs() -> Dict[str, Any]:
    """Return the keyword arguments for Christmas Day at +50%.

    Returns:
        Dict[str, Any]: Constructor keyword arguments.
    """
    return {
        "month": 12,
        "day": 25,
        "surcharge": Decimal("0.50"),
        "label": "Christmas Day",
    }


class TestHolidaySurcharge:
    """Tests for the HolidaySurcharge model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(
        self, valid_holiday_kwargs: Dict[str, Any]
    ) -> None:
        """A holiday is a month, a day, a surcharge and a label."""
        holiday = HolidaySurcharge(**valid_holiday_kwargs)
        assert holiday.month == 12
        assert holiday.day == 25
        assert holiday.surcharge == Decimal("0.50")
        assert holiday.label == "Christmas Day"

    def test_label_is_stripped(self, valid_holiday_kwargs: Dict[str, Any]) -> None:
        """Surrounding whitespace is removed from the label."""
        holiday = HolidaySurcharge(**{**valid_holiday_kwargs, "label": "  Noël  "})
        assert holiday.label == "Noël"

    # ------------------------------------------------------------------ #
    #  month validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("month", [1, 6, 12])
    def test_valid_months_are_accepted(
        self, valid_holiday_kwargs: Dict[str, Any], month: int
    ) -> None:
        """Every month of the year is accepted."""
        assert (
            HolidaySurcharge(**{**valid_holiday_kwargs, "month": month}).month == month
        )

    @pytest.mark.parametrize(
        "invalid_month",
        [
            pytest.param(0, id="Invalid - below range"),
            pytest.param(13, id="Invalid - above range"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param("12", id="Invalid - string"),
            pytest.param(12.0, id="Invalid - float"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_month_raises(
        self, valid_holiday_kwargs: Dict[str, Any], invalid_month: Any
    ) -> None:
        """A month outside 1..12, or not an integer, is rejected."""
        with pytest.raises(MTHolidaySurchargeInvalidMonth):
            HolidaySurcharge(**{**valid_holiday_kwargs, "month": invalid_month})

    # ------------------------------------------------------------------ #
    #  day validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_day",
        [
            pytest.param(0, id="Invalid - below range"),
            pytest.param(32, id="Invalid - above range"),
            pytest.param("25", id="Invalid - string"),
            pytest.param(25.0, id="Invalid - float"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(False, id="Invalid - bool"),
        ],
    )
    def test_invalid_day_raises(
        self, valid_holiday_kwargs: Dict[str, Any], invalid_day: Any
    ) -> None:
        """A day outside 1..31, or not an integer, is rejected."""
        with pytest.raises(MTHolidaySurchargeInvalidDay):
            HolidaySurcharge(**{**valid_holiday_kwargs, "day": invalid_day})

    def test_a_day_that_never_occurs_is_accepted_but_never_matches(
        self, valid_holiday_kwargs: Dict[str, Any]
    ) -> None:
        """30 February validates, and simply matches no real date.

        Notes:
            The validator does not duplicate the calendar's month-length table;
            an impossible day is inert rather than rejected.
        """
        holiday = HolidaySurcharge(**{**valid_holiday_kwargs, "month": 2, "day": 30})
        assert all(not holiday.falls_on(date(2026, 2, day)) for day in range(1, 29))

    # ------------------------------------------------------------------ #
    #  surcharge validation
    # ------------------------------------------------------------------ #

    def test_a_float_surcharge_keeps_its_exact_decimal_value(
        self, valid_holiday_kwargs: Dict[str, Any]
    ) -> None:
        """A YAML float is routed through str, not Decimal(float)."""
        holiday = HolidaySurcharge(**{**valid_holiday_kwargs, "surcharge": 0.5})
        assert holiday.surcharge == Decimal("0.5")

    def test_a_zero_surcharge_is_accepted(
        self, valid_holiday_kwargs: Dict[str, Any]
    ) -> None:
        """A holiday may be listed without an uplift."""
        holiday = HolidaySurcharge(**{**valid_holiday_kwargs, "surcharge": 0})
        assert holiday.surcharge == Decimal("0")

    @pytest.mark.parametrize(
        "invalid_surcharge",
        [
            pytest.param(Decimal("-0.1"), id="Invalid - negative"),
            pytest.param("abc", id="Invalid - unparsable string"),
            pytest.param(None, id="Invalid - None"),
            pytest.param([0.5], id="Invalid - list"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param(Decimal("50"), id="Invalid - percentage not ratio"),
            pytest.param(float("nan"), id="Invalid - NaN"),
        ],
    )
    def test_invalid_surcharge_raises(
        self, valid_holiday_kwargs: Dict[str, Any], invalid_surcharge: Any
    ) -> None:
        """A surcharge that is not a sane non-negative ratio is rejected."""
        with pytest.raises(MTHolidaySurchargeInvalidSurcharge):
            HolidaySurcharge(**{**valid_holiday_kwargs, "surcharge": invalid_surcharge})

    # ------------------------------------------------------------------ #
    #  label validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_label",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(25, id="Invalid - int"),
        ],
    )
    def test_invalid_label_raises(
        self, valid_holiday_kwargs: Dict[str, Any], invalid_label: Any
    ) -> None:
        """A label that is not a non-empty string is rejected."""
        with pytest.raises(MTHolidaySurchargeInvalidLabel):
            HolidaySurcharge(**{**valid_holiday_kwargs, "label": invalid_label})

    # ------------------------------------------------------------------ #
    #  falls_on
    # ------------------------------------------------------------------ #

    def test_falls_on_its_own_date(self, valid_holiday_kwargs: Dict[str, Any]) -> None:
        """The holiday matches its configured month and day."""
        assert HolidaySurcharge(**valid_holiday_kwargs).falls_on(date(2026, 12, 25))

    def test_ignores_the_year(self, valid_holiday_kwargs: Dict[str, Any]) -> None:
        """A fixed-date holiday recurs every year."""
        holiday = HolidaySurcharge(**valid_holiday_kwargs)
        assert holiday.falls_on(date(2027, 12, 25))
        assert holiday.falls_on(date(2035, 12, 25))

    @pytest.mark.parametrize(
        "other_date",
        [
            pytest.param(date(2026, 12, 24), id="day before"),
            pytest.param(date(2026, 12, 26), id="day after"),
            pytest.param(date(2026, 11, 25), id="same day, other month"),
        ],
    )
    def test_does_not_fall_on_other_dates(
        self, valid_holiday_kwargs: Dict[str, Any], other_date: date
    ) -> None:
        """Neighbouring dates do not match."""
        assert HolidaySurcharge(**valid_holiday_kwargs).falls_on(other_date) is False

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTHolidaySurchargeInvalidDay,
            MTHolidaySurchargeInvalidLabel,
            MTHolidaySurchargeInvalidMonth,
            MTHolidaySurchargeInvalidSurcharge,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidHolidaySurchargeException."""
        assert issubclass(exception_class, MTInvalidHolidaySurchargeException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self, valid_holiday_kwargs: Dict[str, Any]) -> None:
        """A holiday survives a dump-and-rebuild unchanged."""
        holiday = HolidaySurcharge(**valid_holiday_kwargs)
        assert HolidaySurcharge(**holiday.model_dump()) == holiday

    def test_max_surcharge_is_not_a_field(
        self, valid_holiday_kwargs: Dict[str, Any]
    ) -> None:
        """The bound is a ClassVar and stays out of the payload."""
        assert (
            "MAX_SURCHARGE" not in HolidaySurcharge(**valid_holiday_kwargs).model_dump()
        )
