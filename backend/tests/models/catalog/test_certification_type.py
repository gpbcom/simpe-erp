from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Any, Dict

# Third-party imports
import pytest

# First-party imports
from models.catalog.certification_type import CertificationType
from models.catalog.exceptions import (
    MTCertificationTypeInvalidCode,
    MTCertificationTypeInvalidDate,
    MTCertificationTypeInvalidDescription,
    MTCertificationTypeInvalidId,
    MTCertificationTypeInvalidIsActive,
    MTCertificationTypeInvalidLabel,
    MTInvalidCertificationTypeException,
)


@pytest.fixture
def valid_kwargs() -> Dict[str, Any]:
    """Return the smallest set of fields a catalogue entry needs.

    Returns:
        Dict[str, Any]: Constructor keywords for a valid entry.
    """
    return {
        "code": "DEAES",
        "label": "Diplôme d'État d'Accompagnant Éducatif et Social",
    }


class TestCertificationType:
    """Tests for the CertificationType model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_code_and_a_label_are_enough(self, valid_kwargs: Dict[str, Any]) -> None:
        """An entry needs only what it is called and what it is keyed by."""
        entry = CertificationType(**valid_kwargs)
        assert entry.code == "DEAES"
        assert entry.description is None
        assert entry.id is None

    def test_an_entry_is_active_by_default(self, valid_kwargs: Dict[str, Any]) -> None:
        """A newly added qualification may be required straight away."""
        assert CertificationType(**valid_kwargs).is_active is True

    def test_full_construction(self, valid_kwargs: Dict[str, Any]) -> None:
        """Every field is accepted together."""
        entry = CertificationType(
            id=" 42 ",
            description="  Diplôme d'État.  ",
            is_active=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            **valid_kwargs,
        )
        assert entry.id == "42"
        assert entry.description == "Diplôme d'État."
        assert entry.is_active is False
        assert entry.created_at == datetime(2026, 1, 1, tzinfo=UTC)

    # ------------------------------------------------------------------ #
    #  code validation
    # ------------------------------------------------------------------ #

    def test_the_code_is_upper_cased(self, valid_kwargs: Dict[str, Any]) -> None:
        """``deaes`` and ``DEAES`` are the same qualification.

        Notes:
            Normalised on the way in because matching is a plain equality test
            in the solver's hot loop; normalising at every comparison would
            make "does this person hold it?" depend on how somebody typed it.
        """
        assert CertificationType(**{**valid_kwargs, "code": " deaes "}).code == "DEAES"

    def test_hyphens_and_underscores_are_accepted(
        self, valid_kwargs: Dict[str, Any]
    ) -> None:
        """The key stays usable in an export or a URL without escaping."""
        entry = CertificationType(**{**valid_kwargs, "code": "SST_1-A"})
        assert entry.code == "SST_1-A"

    @pytest.mark.parametrize(
        "invalid_code",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(7, id="Invalid - int"),
            pytest.param("DE AES", id="Invalid - space"),
            pytest.param("DEAES!", id="Invalid - punctuation"),
            pytest.param("DÉAES", id="Invalid - accent"),
            pytest.param("X" * 33, id="Invalid - too long"),
        ],
    )
    def test_invalid_code_raises(
        self, valid_kwargs: Dict[str, Any], invalid_code: Any
    ) -> None:
        """A code that cannot serve as a stable key is refused."""
        with pytest.raises(MTCertificationTypeInvalidCode):
            CertificationType(**{**valid_kwargs, "code": invalid_code})

    # ------------------------------------------------------------------ #
    #  label validation
    # ------------------------------------------------------------------ #

    def test_the_label_keeps_its_accents(self, valid_kwargs: Dict[str, Any]) -> None:
        """The label is read by a person; the code carries the machine-safe form."""
        entry = CertificationType(**valid_kwargs)
        assert entry.label.startswith("Diplôme d'État")

    def test_the_label_is_stripped(self, valid_kwargs: Dict[str, Any]) -> None:
        """Surrounding whitespace is removed."""
        entry = CertificationType(**{**valid_kwargs, "label": "  Sauveteur  "})
        assert entry.label == "Sauveteur"

    @pytest.mark.parametrize(
        "invalid_label",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_invalid_label_raises(
        self, valid_kwargs: Dict[str, Any], invalid_label: Any
    ) -> None:
        """An entry nobody could identify on screen is refused."""
        with pytest.raises(MTCertificationTypeInvalidLabel):
            CertificationType(**{**valid_kwargs, "label": invalid_label})

    # ------------------------------------------------------------------ #
    #  description validation
    # ------------------------------------------------------------------ #

    def test_a_blank_description_reads_as_absent(
        self, valid_kwargs: Dict[str, Any]
    ) -> None:
        """An emptied text box means "no description", not an empty one."""
        entry = CertificationType(**{**valid_kwargs, "description": "   "})
        assert entry.description is None

    @pytest.mark.parametrize(
        "invalid_description",
        [
            pytest.param(7, id="Invalid - int"),
            pytest.param(["a"], id="Invalid - list"),
        ],
    )
    def test_invalid_description_raises(
        self, valid_kwargs: Dict[str, Any], invalid_description: Any
    ) -> None:
        """A description that is not text is rejected."""
        with pytest.raises(MTCertificationTypeInvalidDescription):
            CertificationType(**{**valid_kwargs, "description": invalid_description})

    # ------------------------------------------------------------------ #
    #  id validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_id",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_invalid_id_raises(
        self, valid_kwargs: Dict[str, Any], invalid_id: Any
    ) -> None:
        """An identifier that is neither None nor a non-empty string is refused."""
        with pytest.raises(MTCertificationTypeInvalidId):
            CertificationType(**{**valid_kwargs, "id": invalid_id})

    # ------------------------------------------------------------------ #
    #  is_active validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_flag",
        [
            pytest.param("false", id="Invalid - string false"),
            pytest.param(0, id="Invalid - int"),
            pytest.param([], id="Invalid - list"),
        ],
    )
    def test_invalid_is_active_raises(
        self, valid_kwargs: Dict[str, Any], invalid_flag: Any
    ) -> None:
        """A retirement flag is a boolean, never a truthy string.

        Notes:
            ``"false"`` is truthy in Python, so a stored one read as "in use"
            would leave an obsolete qualification on offer.
        """
        with pytest.raises(MTCertificationTypeInvalidIsActive):
            CertificationType(**{**valid_kwargs, "is_active": invalid_flag})

    def test_a_none_flag_falls_back_to_active(
        self, valid_kwargs: Dict[str, Any]
    ) -> None:
        """A row written before the column existed reads back as in use."""
        assert CertificationType(**{**valid_kwargs, "is_active": None}).is_active

    # ------------------------------------------------------------------ #
    #  Timestamps
    # ------------------------------------------------------------------ #

    def test_iso_timestamps_are_parsed(self, valid_kwargs: Dict[str, Any]) -> None:
        """A timestamp may arrive as an ISO-8601 string."""
        entry = CertificationType(
            **{**valid_kwargs, "updated_at": "2026-01-01T00:00:00Z"}
        )
        assert entry.updated_at == datetime(2026, 1, 1, tzinfo=UTC)

    @pytest.mark.parametrize(
        "invalid_timestamp",
        [
            pytest.param(20260101, id="Invalid - int"),
            pytest.param(["2026-01-01"], id="Invalid - list"),
        ],
    )
    def test_invalid_timestamp_raises(
        self, valid_kwargs: Dict[str, Any], invalid_timestamp: Any
    ) -> None:
        """A timestamp that is not datetime-like is rejected."""
        with pytest.raises(MTCertificationTypeInvalidDate):
            CertificationType(**{**valid_kwargs, "created_at": invalid_timestamp})

    def test_timestamps_serialize_to_iso_text(
        self, valid_kwargs: Dict[str, Any]
    ) -> None:
        """The store column is text, so a dump hands back a string."""
        entry = CertificationType(
            **{**valid_kwargs, "created_at": datetime(2026, 1, 1, tzinfo=UTC)}
        )
        assert entry.model_dump()["created_at"] == "2026-01-01T00:00:00+00:00"

    # ------------------------------------------------------------------ #
    #  describe
    # ------------------------------------------------------------------ #

    def test_describe_names_both_the_code_and_the_label(
        self, valid_kwargs: Dict[str, Any]
    ) -> None:
        """The planner's diagnosis must be actionable where it is read.

        Notes:
            A manager told only "DEAES is missing" has to go and look the code
            up before they can do anything about it.
        """
        entry = CertificationType(code="SST", label="Sauveteur Secouriste du Travail")
        assert entry.describe() == "SST (Sauveteur Secouriste du Travail)"

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTCertificationTypeInvalidCode,
            MTCertificationTypeInvalidDate,
            MTCertificationTypeInvalidDescription,
            MTCertificationTypeInvalidId,
            MTCertificationTypeInvalidIsActive,
            MTCertificationTypeInvalidLabel,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the model's own family base.

        Notes:
            The API's exception handler walks the ancestry, so one row for the
            family covers every member added later.
        """
        assert issubclass(exception_class, MTInvalidCertificationTypeException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_model_dump_round_trip(self, valid_kwargs: Dict[str, Any]) -> None:
        """An entry survives a dump-and-rebuild unchanged."""
        entry = CertificationType(**valid_kwargs, description="Diplôme.")
        assert CertificationType(**entry.model_dump()) == entry
