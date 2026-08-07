from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Optional, Union

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.enums import ServiceCategory
from models.quoting.exceptions import MTQuoteLineInvalidServiceCategory
from models.quoting.quote_line import QuoteLine


def _line(category: Union[str, ServiceCategory, None] = "necessity") -> QuoteLine:
    """Build a two-hour morning line.

    Args:
        category (Union[str, ServiceCategory, None]): The VAT category.

    Returns:
        QuoteLine: The unpriced line.
    """
    return QuoteLine(
        name="Aide a la toilette",
        intervention_type_id="type-1",
        service_category=category,
        service_date=date(2026, 9, 1),
        earliest_start=time(9, 0),
        latest_end=time(13, 0),
        duration_minutes=120,
    )


class TestQuoteLineServiceCategory:
    """Tests for the VAT category a quote line carries."""

    @pytest.mark.parametrize("category", list(ServiceCategory))
    def test_every_category_is_accepted(self, category: ServiceCategory) -> None:
        """Both kinds of care can be quoted.

        Args:
            category (ServiceCategory): The category under test.
        """
        assert _line(category).service_category is category

    def test_a_string_is_coerced(self) -> None:
        """The browser sends a string; the model stores the enumeration."""
        assert _line("comfort").service_category is ServiceCategory.COMFORT

    @pytest.mark.parametrize("value", [None, "", "luxury", 5, True])
    def test_an_unknown_category_is_refused(self, value: Optional[str]) -> None:
        """A line cannot exist without one.

        Args:
            value (Optional[str]): The rejected category.
        """
        with pytest.raises(MTQuoteLineInvalidServiceCategory):
            _line(value)

    def test_there_is_no_default(self) -> None:
        """**The one decision this field refuses to make quietly.**

        Notes:
            Defaulting to necessity would bill comfort care at 5.5% and
            understate the tax on every line somebody forgot to set — an error
            that surfaces at the tax return rather than on the screen.
            Defaulting to comfort would overcharge families entitled to the
            reduced rate. Neither is worth making silently, so a line without a
            category is not a line.

            Reported as a plain ``ValidationError`` rather than as this model's
            own exception: a ``mode="before"`` validator does not run for a
            field that is absent, so "missing" is Pydantic's finding and
            "unknown" is ours. Both reach the caller as a 422.
        """
        with pytest.raises(ValidationError):
            QuoteLine(
                name="Aide a la toilette",
                intervention_type_id="type-1",
                service_date=date(2026, 9, 1),
                earliest_start=time(9, 0),
                latest_end=time(13, 0),
                duration_minutes=120,
            )

    def test_the_category_decides_the_rate_the_line_is_taxed_at(self) -> None:
        """The whole reason the field moved onto the line."""
        assert (
            _line("necessity").service_category.vat_rate()
            != _line("comfort").service_category.vat_rate()
        )

    def test_two_lines_selling_the_same_service_can_be_taxed_differently(self) -> None:
        """**What the catalogue could never express.**

        Notes:
            The same intervention type, quoted for two customers: help with
            washing under a care plan is necessity care at 5.5%, and the same
            hour arranged privately is comfort care at 20%. While the category
            lived on the catalogue entry, an agency serving both had to keep
            two entries for one service and remember which was which.
        """
        under_a_care_plan = _line(ServiceCategory.NECESSITY)
        arranged_privately = _line(ServiceCategory.COMFORT)

        assert (
            under_a_care_plan.intervention_type_id
            == arranged_privately.intervention_type_id
        )
        assert (
            under_a_care_plan.service_category.vat_rate()
            != arranged_privately.service_category.vat_rate()
        )
