from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.catalog.exceptions import (
    MTInvalidSkillTypeException,
    MTSkillTypeInvalidCode,
    MTSkillTypeInvalidDate,
    MTSkillTypeInvalidDescription,
    MTSkillTypeInvalidId,
    MTSkillTypeInvalidIsActive,
    MTSkillTypeInvalidLabel,
)
from models.catalog.skill_type import SkillType
from tests.annotations import ModelInput


@pytest.fixture
def valid_kwargs() -> Dict[str, ModelInput]:
    """Return the smallest set of fields a catalogue entry needs.

    Returns:
        Dict[str, ModelInput]: Constructor keywords for a valid entry.
    """
    return {
        "code": "LEVE-PERSONNE",
        "label": "Manipulation d'un lève-personne",
    }


class TestSkillType:
    """Tests for the SkillType model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_code_and_a_label_are_enough(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An entry needs only what it is called and what it is keyed by."""
        entry = SkillType(**valid_kwargs)
        assert entry.code == "LEVE-PERSONNE"
        assert entry.description is None
        assert entry.id is None

    def test_an_entry_is_active_by_default(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A newly added skill may be required and declared straight away."""
        assert SkillType(**valid_kwargs).is_active is True

    def test_full_construction(self, valid_kwargs: Dict[str, ModelInput]) -> None:
        """Every field is accepted together."""
        entry = SkillType(
            id=" 42 ",
            description="  Formation interne.  ",
            is_active=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 2, 1, tzinfo=UTC),
            **valid_kwargs,
        )
        assert entry.id == "42"
        assert entry.description == "Formation interne."
        assert entry.is_active is False

    # ------------------------------------------------------------------ #
    #  code
    # ------------------------------------------------------------------ #

    def test_the_code_is_upper_cased(self, valid_kwargs: Dict[str, ModelInput]) -> None:
        """`portugais` and `PORTUGAIS` are the same skill.

        Notes:
            Matching is a plain equality test in the solver's hot loop.
            Normalising at every comparison instead would make "can this person
            do it?" depend on how somebody typed it.
        """
        assert SkillType(**{**valid_kwargs, "code": "  portugais "}).code == "PORTUGAIS"

    @pytest.mark.parametrize("separator", ["-", "_"])
    def test_hyphens_and_underscores_are_allowed(
        self, valid_kwargs: Dict[str, ModelInput], separator: str
    ) -> None:
        """A compound code reads better than a run-together one."""
        code = f"LEVE{separator}PERSONNE"
        assert SkillType(**{**valid_kwargs, "code": code}).code == code

    def test_an_accented_code_is_refused(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The code is ASCII even though the labels are full of accents.

        Notes:
            ``É`` passes :meth:`str.isalnum`, so restricting the alphabet takes
            an explicit test. The code travels into CSV exports and URLs, where
            an accent comes back as two distinct skills.
        """
        with pytest.raises(MTSkillTypeInvalidCode):
            SkillType(**{**valid_kwargs, "code": "LEVÉ"})

    def test_the_label_keeps_its_accents(self) -> None:
        """The label is where the accents belong, and it keeps them."""
        entry = SkillType(code="LEVE", label="  Lève-personne  ")
        assert entry.label == "Lève-personne"

    @pytest.mark.parametrize("code", ["", "   ", None, 42, "A B", "A!"])
    def test_a_malformed_code_is_refused(
        self, valid_kwargs: Dict[str, ModelInput], code: ModelInput
    ) -> None:
        """A code that is not a plain key is refused rather than stored."""
        with pytest.raises(MTSkillTypeInvalidCode):
            SkillType(**{**valid_kwargs, "code": code})

    def test_a_code_longer_than_the_column_is_refused(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The model and the store's column width must agree.

        Notes:
            A model that accepted more than the column holds truncates silently
            on SQLite and errors on PostgreSQL.
        """
        with pytest.raises(MTSkillTypeInvalidCode):
            SkillType(**{**valid_kwargs, "code": "A" * (SkillType.CODE_MAX_LENGTH + 1)})

    def test_a_code_of_exactly_the_limit_is_accepted(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The boundary itself is allowed."""
        code = "A" * SkillType.CODE_MAX_LENGTH
        assert SkillType(**{**valid_kwargs, "code": code}).code == code

    # ------------------------------------------------------------------ #
    #  label, description, is_active
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("label", ["", "   ", None, 42])
    def test_a_blank_label_is_refused(
        self, valid_kwargs: Dict[str, ModelInput], label: ModelInput
    ) -> None:
        """An entry with no label is one nobody can pick with any confidence."""
        with pytest.raises(MTSkillTypeInvalidLabel):
            SkillType(**{**valid_kwargs, "label": label})

    def test_a_blank_description_becomes_none(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Whitespace and absence mean the same thing."""
        assert SkillType(**{**valid_kwargs, "description": "   "}).description is None

    def test_a_non_string_description_is_refused(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A description is text or nothing."""
        with pytest.raises(MTSkillTypeInvalidDescription):
            SkillType(**{**valid_kwargs, "description": 42})

    def test_is_active_defaults_to_true_when_absent(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """``None`` reads as "in use", which is what a fresh entry is."""
        assert SkillType(**{**valid_kwargs, "is_active": None}).is_active is True

    @pytest.mark.parametrize("value", ["false", 0, 1, "true"])
    def test_a_non_boolean_is_active_is_refused(
        self, valid_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """Strings are refused rather than coerced.

        Notes:
            ``"false"`` is truthy, and a retirement read as "still in use"
            would leave an obsolete skill on offer with nothing on screen to
            say the request had not taken.
        """
        with pytest.raises(MTSkillTypeInvalidIsActive):
            SkillType(**{**valid_kwargs, "is_active": value})

    # ------------------------------------------------------------------ #
    #  id and timestamps
    # ------------------------------------------------------------------ #

    def test_an_absent_id_is_allowed(self, valid_kwargs: Dict[str, ModelInput]) -> None:
        """An entry has no identifier until the store gives it one."""
        assert SkillType(**{**valid_kwargs, "id": None}).id is None

    @pytest.mark.parametrize("identifier", ["", "   ", 42])
    def test_a_blank_id_is_refused(
        self, valid_kwargs: Dict[str, ModelInput], identifier: ModelInput
    ) -> None:
        """An empty identifier is not the same as no identifier."""
        with pytest.raises(MTSkillTypeInvalidId):
            SkillType(**{**valid_kwargs, "id": identifier})

    def test_a_non_datetime_timestamp_is_refused(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A timestamp is datetime-like or nothing."""
        with pytest.raises(MTSkillTypeInvalidDate):
            SkillType(**{**valid_kwargs, "created_at": 42})

    def test_timestamps_serialize_to_iso_strings(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The wire carries ISO-8601, not a Python repr."""
        entry = SkillType(
            created_at=datetime(2026, 1, 1, 9, 30, tzinfo=UTC), **valid_kwargs
        )
        assert entry.model_dump()["created_at"] == "2026-01-01T09:30:00+00:00"
        assert entry.model_dump()["updated_at"] is None

    def test_a_dumped_entry_round_trips(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Dumping and rebuilding produces the same entry.

        Notes:
            ``CODE_MAX_LENGTH`` is a :data:`~typing.ClassVar` rather than a bare
            annotation precisely so it stays out of the dump; a bare one would
            put it in every stored payload and break this.
        """
        entry = SkillType(**valid_kwargs)
        assert SkillType(**entry.model_dump()) == entry

    # ------------------------------------------------------------------ #
    #  describe
    # ------------------------------------------------------------------ #

    def test_describe_names_both_the_code_and_the_label(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A manager told only the code has to go and look it up.

        Notes:
            This string reaches the planner's unplaced-work diagnosis, which is
            read by somebody deciding what to do about it this afternoon.
        """
        assert SkillType(**valid_kwargs).describe() == (
            "LEVE-PERSONNE (Manipulation d'un lève-personne)"
        )

    # ------------------------------------------------------------------ #
    #  Exception family
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception",
        [
            MTSkillTypeInvalidCode,
            MTSkillTypeInvalidDate,
            MTSkillTypeInvalidDescription,
            MTSkillTypeInvalidId,
            MTSkillTypeInvalidIsActive,
            MTSkillTypeInvalidLabel,
        ],
    )
    def test_every_failure_belongs_to_one_family(self, exception: type) -> None:
        """One ``except`` catches every way this model can refuse a value.

        Notes:
            The API's handler table maps the family, not each member, so a new
            member answers 422 rather than 500 without anybody remembering to
            add a row.
        """
        assert issubclass(exception, MTInvalidSkillTypeException)
