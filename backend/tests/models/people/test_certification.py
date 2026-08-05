from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime
from typing import Any

# Third-party imports
import pytest

# First-party imports
from models.people.certification import Certification
from models.people.exceptions import (
    MTCertificationInvalidExpiresOn,
    MTCertificationInvalidIssuer,
    MTCertificationInvalidName,
    MTCertificationInvalidObtainedOn,
    MTInvalidCertificationException,
)


class TestCertification:
    """Tests for the Certification model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_only_the_name_is_required(self) -> None:
        """A qualification can be recorded from its name alone.

        Notes:
            Certifications are captured from paper records of varying
            completeness; requiring a date would push managers to invent one.
        """
        certification = Certification(name="DEAVS")
        assert certification.name == "DEAVS"
        assert certification.issuer is None
        assert certification.obtained_on is None
        assert certification.expires_on is None

    def test_full_construction(self) -> None:
        """Every field is accepted together."""
        certification = Certification(
            name="Premiers secours",
            issuer="Croix-Rouge",
            obtained_on=date(2024, 3, 1),
            expires_on=date(2027, 3, 1),
        )
        assert certification.issuer == "Croix-Rouge"
        assert certification.expires_on == date(2027, 3, 1)

    @pytest.mark.parametrize("field", ["name", "issuer"])
    def test_text_fields_are_stripped(self, field: str) -> None:
        """Surrounding whitespace is removed."""
        certification = Certification(**{"name": "DEAVS", field: "  Value  "})
        assert getattr(certification, field) == "Value"

    def test_iso_date_strings_are_parsed(self) -> None:
        """A date may be supplied as an ISO-8601 string."""
        certification = Certification(name="DEAVS", obtained_on="2024-03-01")
        assert certification.obtained_on == date(2024, 3, 1)

    def test_a_datetime_is_narrowed_to_its_date(self) -> None:
        """A midnight timestamp is read as the date it represents.

        Notes:
            Source records sometimes carry a timestamp where a plain date was
            meant; narrowing is kinder than rejecting.
        """
        certification = Certification(
            name="DEAVS", obtained_on=datetime(2024, 3, 1, 0, 0, tzinfo=UTC)
        )
        assert certification.obtained_on == date(2024, 3, 1)

    # ------------------------------------------------------------------ #
    #  name validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_invalid_name_raises(self, invalid_name: Any) -> None:
        """A name that is not a non-empty string is rejected."""
        with pytest.raises(MTCertificationInvalidName):
            Certification(name=invalid_name)

    # ------------------------------------------------------------------ #
    #  issuer validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_issuer",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_invalid_issuer_raises(self, invalid_issuer: Any) -> None:
        """An issuer that is neither None nor a non-empty string is rejected."""
        with pytest.raises(MTCertificationInvalidIssuer):
            Certification(name="DEAVS", issuer=invalid_issuer)

    # ------------------------------------------------------------------ #
    #  date validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_date",
        [
            pytest.param(20240301, id="Invalid - int"),
            pytest.param([2024, 3, 1], id="Invalid - list"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_invalid_obtained_on_raises(self, invalid_date: Any) -> None:
        """A non date-like obtained_on is rejected."""
        with pytest.raises(MTCertificationInvalidObtainedOn):
            Certification(name="DEAVS", obtained_on=invalid_date)

    @pytest.mark.parametrize(
        "invalid_date",
        [
            pytest.param(20270301, id="Invalid - int"),
            pytest.param({}, id="Invalid - dict"),
        ],
    )
    def test_invalid_expires_on_raises(self, invalid_date: Any) -> None:
        """A non date-like expires_on is rejected."""
        with pytest.raises(MTCertificationInvalidExpiresOn):
            Certification(name="DEAVS", expires_on=invalid_date)

    # ------------------------------------------------------------------ #
    #  Cross-field validation
    # ------------------------------------------------------------------ #

    def test_expiry_before_award_raises(self) -> None:
        """A qualification cannot lapse before it was awarded."""
        with pytest.raises(MTCertificationInvalidExpiresOn):
            Certification(
                name="DEAVS",
                obtained_on=date(2024, 3, 1),
                expires_on=date(2023, 3, 1),
            )

    def test_expiry_on_the_award_date_is_accepted(self) -> None:
        """A same-day expiry is degenerate but not contradictory."""
        certification = Certification(
            name="DEAVS",
            obtained_on=date(2024, 3, 1),
            expires_on=date(2024, 3, 1),
        )
        assert certification.expires_on == certification.obtained_on

    def test_one_sided_dates_skip_the_comparison(self) -> None:
        """The bound is only checked when both dates are known."""
        assert Certification(name="DEAVS", expires_on=date(2020, 1, 1)).expires_on

    # ------------------------------------------------------------------ #
    #  is_expired_on
    # ------------------------------------------------------------------ #

    def test_a_certification_without_expiry_never_lapses(self) -> None:
        """No recorded expiry means the qualification stands indefinitely."""
        assert Certification(name="DEAVS").is_expired_on(date(2099, 1, 1)) is False

    def test_expired_before_the_reference_date(self) -> None:
        """A qualification that lapsed yesterday is expired today."""
        certification = Certification(name="DEAVS", expires_on=date(2026, 8, 4))
        assert certification.is_expired_on(date(2026, 8, 5)) is True

    def test_not_expired_on_the_expiry_date_itself(self) -> None:
        """The qualification is still valid on its last day."""
        certification = Certification(name="DEAVS", expires_on=date(2026, 8, 5))
        assert certification.is_expired_on(date(2026, 8, 5)) is False

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTCertificationInvalidExpiresOn,
            MTCertificationInvalidIssuer,
            MTCertificationInvalidName,
            MTCertificationInvalidObtainedOn,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from MTInvalidCertificationException."""
        assert issubclass(exception_class, MTInvalidCertificationException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self) -> None:
        """A qualification survives a dump-and-rebuild unchanged."""
        certification = Certification(
            name="DEAVS", issuer="État", obtained_on=date(2024, 3, 1)
        )
        assert Certification(**certification.model_dump()) == certification
