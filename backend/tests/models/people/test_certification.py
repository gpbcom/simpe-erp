from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime

# Third-party imports
import pytest

# First-party imports
from models.people.hca.certification import Certification
from models.people.hca.exceptions import (
    MTCertificationInvalidCode,
    MTCertificationInvalidExpiresOn,
    MTCertificationInvalidIssuer,
    MTCertificationInvalidName,
    MTCertificationInvalidObtainedOn,
    MTInvalidCertificationException,
)
from tests.annotations import ModelInput


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
            meant. Narrowing is kinder than rejecting.
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
    def test_invalid_name_raises(self, invalid_name: ModelInput) -> None:
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
    def test_invalid_issuer_raises(self, invalid_issuer: ModelInput) -> None:
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
    def test_invalid_obtained_on_raises(self, invalid_date: ModelInput) -> None:
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
    def test_invalid_expires_on_raises(self, invalid_date: ModelInput) -> None:
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
    #  code validation
    # ------------------------------------------------------------------ #

    def test_a_qualification_carries_no_code_by_default(self) -> None:
        """A free-text record is still a record. The catalogue link is optional."""
        assert Certification(name="DEAVS").code is None

    def test_a_code_is_upper_cased(self) -> None:
        """Matching is a plain equality test, so the case is fixed on the way in."""
        assert Certification(name="DEAVS", code=" deavs ").code == "DEAVS"

    def test_a_blank_code_reads_as_absent(self) -> None:
        """An empty select must still save.

        Notes:
            A form that submits an empty string means "not from the
            catalogue", which is the same state as never having chosen one.
        """
        assert Certification(name="DEAVS", code="   ").code is None

    @pytest.mark.parametrize(
        "invalid_code",
        [
            pytest.param("DE AVS", id="Invalid - space"),
            pytest.param("DEAVS!", id="Invalid - punctuation"),
            pytest.param("DÉAVS", id="Invalid - accent"),
            pytest.param("X" * 33, id="Invalid - too long"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_invalid_code_raises(self, invalid_code: ModelInput) -> None:
        """A code that could not be matched is refused rather than stored."""
        with pytest.raises(MTCertificationInvalidCode):
            Certification(name="DEAVS", code=invalid_code)

    def test_hyphens_and_underscores_are_accepted(self) -> None:
        """A code stays usable as a stable key in an export or a URL."""
        assert Certification(name="x", code="SST_1-A").code == "SST_1-A"

    # ------------------------------------------------------------------ #
    #  satisfies
    # ------------------------------------------------------------------ #

    def test_satisfies_its_own_code(self) -> None:
        """A held qualification meets a requirement naming its code."""
        held = Certification(name="DEAVS", code="DEAVS")
        assert held.satisfies("DEAVS", date(2026, 8, 5)) is True

    def test_does_not_satisfy_another_code(self) -> None:
        """A different qualification is not a substitute."""
        held = Certification(name="DEAVS", code="DEAVS")
        assert held.satisfies("SST", date(2026, 8, 5)) is False

    def test_an_untyped_qualification_satisfies_nothing(self) -> None:
        """A free-text name is a record, not a claim that can be matched.

        Notes:
            Matching on the name would let a spelling decide who is qualified.
        """
        assert Certification(name="DEAVS").satisfies("DEAVS", date(2026, 8, 5)) is False

    def test_a_lapsed_qualification_does_not_satisfy(self) -> None:
        """Expiry is tested against the day of the visit, not against today."""
        held = Certification(name="SST", code="SST", expires_on=date(2026, 8, 4))
        assert held.satisfies("SST", date(2026, 8, 5)) is False

    def test_it_still_satisfies_on_its_last_day(self) -> None:
        """A certificate is valid up to and including the day it lapses."""
        held = Certification(name="SST", code="SST", expires_on=date(2026, 8, 5))
        assert held.satisfies("SST", date(2026, 8, 5)) is True

    def test_the_same_holder_qualifies_for_one_day_and_not_the_next(self) -> None:
        """The visit's own date decides, which is what a plan made ahead needs.

        Notes:
            This is the case a check against "now" would get wrong: the
            certificate is valid when the solver runs and lapsed by the time
            somebody is due at the door.
        """
        held = Certification(name="SST", code="SST", expires_on=date(2026, 8, 5))
        assert held.satisfies("SST", date(2026, 8, 5)) is True
        assert held.satisfies("SST", date(2026, 8, 6)) is False

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTCertificationInvalidCode,
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
