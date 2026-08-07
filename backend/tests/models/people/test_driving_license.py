from __future__ import annotations

# Standard library imports
from datetime import date
from typing import Any, List

# Third-party imports
import pytest

# First-party imports
from models.people.hca.driving_license import DrivingLicense
from models.people.hca.exceptions import (
    MTDrivingLicenseInvalidCategories,
    MTDrivingLicenseInvalidExpiresOn,
    MTDrivingLicenseInvalidNumber,
    MTDrivingLicenseInvalidObtainedOn,
    MTInvalidDrivingLicenseException,
)


class TestDrivingLicense:
    """Tests for the DrivingLicense model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_an_empty_licence_is_valid(self) -> None:
        """Every field is optional; an empty record holds no categories."""
        licence = DrivingLicense()
        assert licence.categories == []
        assert licence.number is None

    def test_full_construction(self) -> None:
        """Every field is accepted together."""
        licence = DrivingLicense(
            categories=["B"],
            number="12AB34567",
            obtained_on=date(2015, 6, 1),
            expires_on=date(2030, 6, 1),
        )
        assert licence.number == "12AB34567"
        assert licence.categories == ["B"]

    # ------------------------------------------------------------------ #
    #  categories validation
    # ------------------------------------------------------------------ #

    def test_categories_are_upper_cased(self) -> None:
        """A lower-case category is normalised."""
        assert DrivingLicense(categories=["b", "a2"]).categories == ["B", "A2"]

    def test_categories_are_deduplicated_preserving_order(self) -> None:
        """Repeats collapse but the paper order is kept.

        Notes:
            Sorting would be tidier but would stop the stored value reading the
            way the physical licence does.
        """
        licence = DrivingLicense(categories=["D", "B", "b", "A2", "D"])
        assert licence.categories == ["D", "B", "A2"]

    def test_none_categories_yields_an_empty_list(self) -> None:
        """An absent list is empty, not an error."""
        assert DrivingLicense(categories=None).categories == []

    @pytest.mark.parametrize(
        "invalid_categories",
        [
            pytest.param("B", id="Invalid - string not list"),
            pytest.param({"B": True}, id="Invalid - mapping"),
        ],
    )
    def test_invalid_categories_container_raises(self, invalid_categories: Any) -> None:
        """The categories must be a list."""
        with pytest.raises(MTDrivingLicenseInvalidCategories):
            DrivingLicense(categories=invalid_categories)

    @pytest.mark.parametrize(
        "invalid_entry",
        [
            pytest.param("Z", id="Invalid - unknown category"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(1, id="Invalid - int"),
        ],
    )
    def test_invalid_category_entry_raises(self, invalid_entry: Any) -> None:
        """An entry that is not a known licence category is rejected."""
        with pytest.raises(MTDrivingLicenseInvalidCategories):
            DrivingLicense(categories=[invalid_entry])

    @pytest.mark.parametrize("category", ["AM", "A1", "A2", "A", "B", "BE", "C", "D"])
    def test_known_categories_are_accepted(self, category: str) -> None:
        """Each recognised European category is accepted."""
        assert DrivingLicense(categories=[category]).categories == [category]

    # ------------------------------------------------------------------ #
    #  number validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_number",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(12345, id="Invalid - int"),
        ],
    )
    def test_invalid_number_raises(self, invalid_number: Any) -> None:
        """A number that is neither None nor a non-empty string is rejected."""
        with pytest.raises(MTDrivingLicenseInvalidNumber):
            DrivingLicense(number=invalid_number)

    # ------------------------------------------------------------------ #
    #  date validation
    # ------------------------------------------------------------------ #

    def test_invalid_obtained_on_raises(self) -> None:
        """A non date-like obtained_on is rejected."""
        with pytest.raises(MTDrivingLicenseInvalidObtainedOn):
            DrivingLicense(obtained_on=20150601)

    def test_invalid_expires_on_raises(self) -> None:
        """A non date-like expires_on is rejected."""
        with pytest.raises(MTDrivingLicenseInvalidExpiresOn):
            DrivingLicense(expires_on=[2030, 6, 1])

    def test_renewal_before_issue_raises(self) -> None:
        """A licence cannot expire before it was issued."""
        with pytest.raises(MTDrivingLicenseInvalidExpiresOn):
            DrivingLicense(obtained_on=date(2015, 6, 1), expires_on=date(2010, 6, 1))

    # ------------------------------------------------------------------ #
    #  can_drive_a_car
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("categories", "expected"),
        [
            pytest.param(["B"], True, id="car licence"),
            pytest.param(["B1"], True, id="light car licence"),
            pytest.param(["BE"], True, id="car with trailer"),
            pytest.param(["A2"], False, id="motorcycle only"),
            pytest.param(["AM"], False, id="moped only"),
            pytest.param([], False, id="no category"),
            pytest.param(["A2", "B"], True, id="motorcycle plus car"),
            pytest.param(["C"], False, id="lorry only"),
        ],
    )
    def test_can_drive_a_car(self, categories: List[str], expected: bool) -> None:
        """Only a car category permits routing at driving speed.

        Notes:
            A motorcycle-only licence must not be read as "can drive": the
            planner would route the assistant at car speed on a vehicle they
            cannot use for the job.
        """
        assert DrivingLicense(categories=categories).can_drive_a_car() is expected

    # ------------------------------------------------------------------ #
    #  is_expired_on
    # ------------------------------------------------------------------ #

    def test_a_licence_without_expiry_never_lapses(self) -> None:
        """No recorded renewal date means the licence stands."""
        assert DrivingLicense(categories=["B"]).is_expired_on(date(2099, 1, 1)) is False

    def test_expired_before_the_reference_date(self) -> None:
        """A licence that lapsed yesterday is expired today."""
        licence = DrivingLicense(categories=["B"], expires_on=date(2026, 8, 4))
        assert licence.is_expired_on(date(2026, 8, 5)) is True

    def test_not_expired_on_the_expiry_date_itself(self) -> None:
        """The licence is still valid on its last day."""
        licence = DrivingLicense(categories=["B"], expires_on=date(2026, 8, 5))
        assert licence.is_expired_on(date(2026, 8, 5)) is False

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTDrivingLicenseInvalidCategories,
            MTDrivingLicenseInvalidExpiresOn,
            MTDrivingLicenseInvalidNumber,
            MTDrivingLicenseInvalidObtainedOn,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidDrivingLicenseException."""
        assert issubclass(exception_class, MTInvalidDrivingLicenseException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self) -> None:
        """A licence survives a dump-and-rebuild unchanged."""
        licence = DrivingLicense(categories=["B"], number="12AB34567")
        assert DrivingLicense(**licence.model_dump()) == licence

    def test_class_constants_are_not_fields(self) -> None:
        """ClassVars stay out of the serialised payload."""
        dumped = DrivingLicense().model_dump()
        assert "KNOWN_CATEGORIES" not in dumped
        assert "CAR_CATEGORIES" not in dumped
