from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime

# Third-party imports
import pytest

# First-party imports
from models.people.hca.exceptions import (
    MTInvalidSkillException,
    MTSkillInvalidCode,
    MTSkillInvalidExpiresOn,
    MTSkillInvalidId,
    MTSkillInvalidIssuer,
    MTSkillInvalidName,
    MTSkillInvalidObtainedOn,
)
from models.people.hca.skill import Skill


class TestSkill:
    """Tests for the Skill model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_only_the_name_is_required(self) -> None:
        """A skill can be declared from its name alone.

        Notes:
            A skill is self-declared. Refusing one because its date is unknown
            would push people to invent a date or to not declare it — and an
            undeclared skill is a visit nobody gets assigned to.
        """
        skill = Skill(name="Portugais")
        assert skill.name == "Portugais"
        assert skill.id is None
        assert skill.code is None
        assert skill.issuer is None
        assert skill.obtained_on is None
        assert skill.expires_on is None

    def test_full_construction(self) -> None:
        """Every field is accepted together."""
        skill = Skill(
            id=" 42 ",
            name="  Lève-personne  ",
            code=" leve-personne ",
            issuer="  Formation interne  ",
            obtained_on=date(2024, 3, 1),
            expires_on=date(2027, 3, 1),
        )
        assert skill.id == "42"
        assert skill.name == "Lève-personne"
        assert skill.code == "LEVE-PERSONNE"
        assert skill.issuer == "Formation interne"

    # ------------------------------------------------------------------ #
    #  id — the field a certification does not have
    # ------------------------------------------------------------------ #

    def test_a_skill_carries_an_identifier(self) -> None:
        """Unlike a certification, a skill is addressed one at a time.

        Notes:
            It is deleted by its owner, a manager or an administrator, and
            every one of those names a single record. Without an identifier the
            only way to delete one would be to match on its fields, which
            cannot tell two skills entered under the same name apart.
        """
        assert "id" in Skill.model_fields

    def test_a_skill_carries_no_owner(self) -> None:
        """There is deliberately no ``hca_id`` to send.

        Notes:
            The owning assistant comes from the route and is applied by the
            repository, so a payload cannot file a skill against a colleague.
            The absence *is* the control.
        """
        assert "hca_id" not in Skill.model_fields

    @pytest.mark.parametrize("identifier", ["", "   ", 42])
    def test_a_blank_id_is_refused(self, identifier: object) -> None:
        """A blank identifier would address no row and report success."""
        with pytest.raises(MTSkillInvalidId):
            Skill(name="Portugais", id=identifier)

    # ------------------------------------------------------------------ #
    #  name and code
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("name", ["", "   ", None, 42])
    def test_a_blank_name_is_refused(self, name: object) -> None:
        """A skill with no name is not a record anybody keeps."""
        with pytest.raises(MTSkillInvalidName):
            Skill(name=name)

    def test_the_code_is_upper_cased(self) -> None:
        """A code that reached the solver in the wrong case would match nobody."""
        assert Skill(name="Portugais", code="portugais").code == "PORTUGAIS"

    def test_a_blank_code_reads_as_not_from_the_catalogue(self) -> None:
        """An empty select must still save.

        Notes:
            The self-service form offers exactly that, and refusing it would
            stop somebody recording a skill the catalogue has no name for yet.
        """
        assert Skill(name="Bricolage", code="   ").code is None

    @pytest.mark.parametrize("code", [42, "A B", "LEVÉ", "A!"])
    def test_a_malformed_code_is_refused(self, code: object) -> None:
        """A malformed code would match nothing and leave its holder unskilled."""
        with pytest.raises(MTSkillInvalidCode):
            Skill(name="Portugais", code=code)

    def test_a_code_longer_than_the_column_is_refused(self) -> None:
        """The model and the catalogue's own limit must agree."""
        with pytest.raises(MTSkillInvalidCode):
            Skill(name="Portugais", code="A" * (Skill.CODE_MAX_LENGTH + 1))

    def test_the_code_rule_matches_the_catalogue(self) -> None:
        """The two models must accept exactly the same keys.

        Notes:
            The rule is a deliberate copy rather than a shared helper — a
            helper would have to live outside both classes, and importing the
            catalogue here would make a person's record depend on it. A test is
            what keeps the copies honest.
        """
        # First-party imports
        from models.catalog.skill_type import SkillType

        assert Skill.CODE_MAX_LENGTH == SkillType.CODE_MAX_LENGTH
        for code in ("LEVE-PERSONNE", "A_B", "AB12"):
            assert (
                Skill(name="x", code=code).code == SkillType(code=code, label="x").code
            )

    # ------------------------------------------------------------------ #
    #  issuer and dates
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("issuer", ["", "   ", 42])
    def test_a_blank_issuer_is_refused(self, issuer: object) -> None:
        """An issuer is a name or nothing, never an empty string."""
        with pytest.raises(MTSkillInvalidIssuer):
            Skill(name="Portugais", issuer=issuer)

    def test_a_datetime_is_narrowed_to_its_date(self) -> None:
        """A date picker submitting midnight is the honest case."""
        skill = Skill(name="x", obtained_on=datetime(2024, 3, 1, 0, 0, tzinfo=UTC))
        assert skill.obtained_on == date(2024, 3, 1)

    def test_a_non_date_obtained_on_is_refused(self) -> None:
        """An acquisition date is date-like or nothing."""
        with pytest.raises(MTSkillInvalidObtainedOn):
            Skill(name="x", obtained_on=42)

    def test_a_non_date_expires_on_is_refused(self) -> None:
        """An expiry is date-like or nothing."""
        with pytest.raises(MTSkillInvalidExpiresOn):
            Skill(name="x", expires_on=42)

    def test_an_expiry_before_the_acquisition_is_refused(self) -> None:
        """A skill cannot lapse before it was acquired."""
        with pytest.raises(MTSkillInvalidExpiresOn):
            Skill(name="x", obtained_on=date(2026, 1, 1), expires_on=date(2025, 1, 1))

    def test_an_expiry_on_the_acquisition_day_is_allowed(self) -> None:
        """The boundary itself is a real, if brief, skill."""
        skill = Skill(
            name="x", obtained_on=date(2026, 1, 1), expires_on=date(2026, 1, 1)
        )
        assert skill.expires_on == date(2026, 1, 1)

    # ------------------------------------------------------------------ #
    #  is_expired_on
    # ------------------------------------------------------------------ #

    def test_a_skill_with_no_expiry_never_lapses(self) -> None:
        """Most declared skills do not expire at all."""
        assert Skill(name="x").is_expired_on(date(2099, 1, 1)) is False

    def test_a_skill_lapses_strictly_after_its_expiry(self) -> None:
        """The expiry day itself is still covered."""
        skill = Skill(name="x", expires_on=date(2026, 6, 1))
        assert skill.is_expired_on(date(2026, 6, 1)) is False
        assert skill.is_expired_on(date(2026, 6, 2)) is True

    # ------------------------------------------------------------------ #
    #  satisfies
    # ------------------------------------------------------------------ #

    def test_an_uncoded_skill_satisfies_nothing(self) -> None:
        """A free-text name is not a claim the agency can match against.

        Notes:
            Treating an untyped name as a match would let a spelling decide who
            is qualified.
        """
        assert (
            Skill(name="LEVE-PERSONNE").satisfies("LEVE-PERSONNE", date(2026, 1, 1))
            is False
        )

    def test_a_coded_skill_satisfies_its_own_code(self) -> None:
        """The ordinary case."""
        skill = Skill(name="Lève-personne", code="LEVE-PERSONNE")
        assert skill.satisfies("LEVE-PERSONNE", date(2026, 1, 1)) is True

    def test_a_coded_skill_satisfies_nothing_else(self) -> None:
        """Matching is exact equality on the code."""
        skill = Skill(name="Lève-personne", code="LEVE-PERSONNE")
        assert skill.satisfies("TOILETTE", date(2026, 1, 1)) is False

    def test_the_expiry_is_judged_on_the_day_of_the_visit(self) -> None:
        """A refresher that lapses on Friday covers Thursday and not Monday.

        Notes:
            This is the whole reason ``satisfies`` takes a date. Checking
            against the moment the solver runs would either send somebody out
            unqualified or hold back work they can legitimately do.
        """
        skill = Skill(name="x", code="SST", expires_on=date(2026, 6, 5))
        assert skill.satisfies("SST", date(2026, 6, 4)) is True
        assert skill.satisfies("SST", date(2026, 6, 8)) is False

    # ------------------------------------------------------------------ #
    #  Exception family
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception",
        [
            MTSkillInvalidCode,
            MTSkillInvalidExpiresOn,
            MTSkillInvalidId,
            MTSkillInvalidIssuer,
            MTSkillInvalidName,
            MTSkillInvalidObtainedOn,
        ],
    )
    def test_every_failure_belongs_to_one_family(self, exception: type) -> None:
        """One ``except`` catches every way this model can refuse a value."""
        assert issubclass(exception, MTInvalidSkillException)
