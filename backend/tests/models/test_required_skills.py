from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.catalog.exceptions import MTInterventionTypeInvalidRequiredSkills
from models.catalog.intervention_type import InterventionType
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.people.hca.skill import Skill
from models.planning.intervention.exceptions import MTRequirementInvalidRequiredSkills
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.quoting.exceptions import MTQuoteLineInvalidRequiredSkills
from models.quoting.quote_line import QuoteLine
from models.schemas.exceptions import MTInterventionTypeUpdateRequestInvalidSkills
from models.schemas.requests.catalog.intervention_type_update_request import (
    InterventionTypeUpdateRequest,
)
from tests.annotations import ModelInput


@pytest.fixture
def valid_type_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid catalogue entry.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {
        "name": "Soin infirmier",
        "code": "SOIN",
        "service_category": "necessity",
    }


@pytest.fixture
def valid_line_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid quote line.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {
        "name": "Soin infirmier",
        "intervention_type_id": "type-1",
        "service_category": "necessity",
        "service_date": date(2026, 8, 5),
        "earliest_start": time(9, 0),
        "latest_end": time(11, 0),
        "duration_minutes": 60,
    }


@pytest.fixture
def valid_requirement_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid solver requirement.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {
        "id": "req-1",
        "quote_line_id": "line-1",
        "customer_id": "customer-1",
        "name": "Soin infirmier",
        "intervention_type_id": "type-1",
        "day": date(2026, 8, 5),
        "window_start_minute": 540,
        "window_end_minute": 660,
        "duration_minutes": 60,
        "location": GeoPoint(latitude=48.85, longitude=2.35),
    }


@pytest.fixture
def valid_hca_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid assistant.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {
        "first_name": "Luc",
        "last_name": "Martin",
        "phone_number": "+33600000001",
        "email": "luc.martin@simple-erp.fr",
        "address": {
            "street": "5 avenue de la Gare",
            "postal_code": "75012",
            "city": "Paris",
            "country": "France",
        },
        "company_id": "company-1",
        "contract_type": "cdi",
    }


class TestRequiredSkills:
    """Tests for the skill requirement carried from catalogue to solver."""

    # ------------------------------------------------------------------ #
    #  InterventionType — the catalogue default
    # ------------------------------------------------------------------ #

    def test_a_catalogue_entry_requires_no_skill_by_default(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Adding the field changed nothing about work already sold."""
        assert InterventionType(**valid_type_kwargs).required_skill_codes == []

    def test_catalogue_codes_are_normalised(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Upper-cased on the way in so matching is a plain equality test."""
        entry = InterventionType(
            **valid_type_kwargs, required_skill_codes=["leve-personne", " toilette "]
        )
        assert entry.required_skill_codes == ["LEVE-PERSONNE", "TOILETTE"]

    def test_catalogue_codes_are_de_duplicated(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The same code twice means what it means once."""
        entry = InterventionType(
            **valid_type_kwargs, required_skill_codes=["TOILETTE", "toilette"]
        )
        assert entry.required_skill_codes == ["TOILETTE"]

    @pytest.mark.parametrize("invalid", ["TOILETTE", 42, [""], ["  "], [42], [None]])
    def test_a_malformed_catalogue_requirement_is_refused(
        self, valid_type_kwargs: Dict[str, ModelInput], invalid: ModelInput
    ) -> None:
        """A malformed requirement is refused rather than silently dropped."""
        with pytest.raises(MTInterventionTypeInvalidRequiredSkills):
            InterventionType(**valid_type_kwargs, required_skill_codes=invalid)

    def test_the_two_requirement_lists_are_independent(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A service may need a diploma, a skill, both or neither.

        Notes:
            One merged list would collapse two unplaced reasons into one and
            send managers to the wrong screen.
        """
        entry = InterventionType(
            **valid_type_kwargs,
            required_certification_codes=["DEAES"],
            required_skill_codes=["TOILETTE"],
        )
        assert entry.required_certification_codes == ["DEAES"]
        assert entry.required_skill_codes == ["TOILETTE"]

    def test_a_malformed_skill_names_the_skill_exception(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The message must send whoever reads it to the right catalogue."""
        with pytest.raises(MTInterventionTypeInvalidRequiredSkills) as raised:
            InterventionType(**valid_type_kwargs, required_skill_codes=[""])
        assert "skill" in str(raised.value)

    # ------------------------------------------------------------------ #
    #  QuoteLine — the three-state override
    # ------------------------------------------------------------------ #

    def test_a_line_inherits_by_default(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """``None`` means "whatever the catalogue entry requires"."""
        assert QuoteLine(**valid_line_kwargs).required_skill_codes is None

    def test_a_line_may_override(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An array means "these, instead of the catalogue's"."""
        line = QuoteLine(**valid_line_kwargs, required_skill_codes=["toilette"])
        assert line.required_skill_codes == ["TOILETTE"]

    def test_an_empty_override_survives_as_one(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An empty array means "this hour needs no skill at all".

        Notes:
            Collapsing it into ``None`` would silently reinstate a requirement
            the person writing the quote had deliberately removed.
        """
        assert (
            QuoteLine(**valid_line_kwargs, required_skill_codes=[]).required_skill_codes
            == []
        )

    @pytest.mark.parametrize("invalid", ["TOILETTE", 42, [""], [42]])
    def test_a_malformed_line_override_is_refused(
        self, valid_line_kwargs: Dict[str, ModelInput], invalid: ModelInput
    ) -> None:
        """A malformed override is refused rather than stored."""
        with pytest.raises(MTQuoteLineInvalidRequiredSkills):
            QuoteLine(**valid_line_kwargs, required_skill_codes=invalid)

    def test_effective_codes_fall_back_to_the_catalogue(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """No override means the catalogue's."""
        line = QuoteLine(**valid_line_kwargs)
        assert line.effective_skill_codes(["TOILETTE"]) == ["TOILETTE"]

    def test_effective_codes_honour_an_override(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An override wins over the catalogue's default."""
        line = QuoteLine(**valid_line_kwargs, required_skill_codes=["ARABE"])
        assert line.effective_skill_codes(["TOILETTE"]) == ["ARABE"]

    def test_an_empty_override_is_honoured_not_treated_as_absent(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The distinction is the whole reason the field is nullable."""
        line = QuoteLine(**valid_line_kwargs, required_skill_codes=[])
        assert line.effective_skill_codes(["TOILETTE"]) == []

    def test_the_two_overrides_resolve_independently(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A line may keep the catalogue's diplomas and drop its skills."""
        line = QuoteLine(**valid_line_kwargs, required_skill_codes=[])
        assert line.effective_certification_codes(["DEAES"]) == ["DEAES"]
        assert line.effective_skill_codes(["TOILETTE"]) == []

    # ------------------------------------------------------------------ #
    #  InterventionRequirement — what the solver actually sees
    # ------------------------------------------------------------------ #

    def test_a_requirement_needs_no_skill_by_default(
        self, valid_requirement_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Most work needs nothing, which is what makes the skip worthwhile."""
        requirement = InterventionRequirement(**valid_requirement_kwargs)
        assert requirement.required_skill_codes == []
        assert requirement.requires_skills() is False

    def test_a_requirement_reports_that_it_needs_a_skill(
        self, valid_requirement_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The solver adds its constraint only for these."""
        requirement = InterventionRequirement(
            **valid_requirement_kwargs, required_skill_codes=["TOILETTE"]
        )
        assert requirement.requires_skills() is True

    def test_requirement_codes_are_normalised_and_de_duplicated(
        self, valid_requirement_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Normalised again here, because a requirement is also built directly.

        Notes:
            A code that reached the solver in the wrong case would match nobody
            and fail the run with a reason that looks like a staffing problem.
        """
        requirement = InterventionRequirement(
            **valid_requirement_kwargs,
            required_skill_codes=["toilette", "TOILETTE", " arabe "],
        )
        assert requirement.required_skill_codes == ["TOILETTE", "ARABE"]

    @pytest.mark.parametrize("invalid", ["TOILETTE", 42, [""], [42]])
    def test_a_malformed_requirement_is_refused(
        self, valid_requirement_kwargs: Dict[str, ModelInput], invalid: ModelInput
    ) -> None:
        """The solver never sees a requirement it cannot match."""
        with pytest.raises(MTRequirementInvalidRequiredSkills):
            InterventionRequirement(
                **valid_requirement_kwargs, required_skill_codes=invalid
            )

    def test_the_two_requirements_reach_the_solver_separately(
        self, valid_requirement_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Kept apart all the way in, so the diagnosis can tell them apart."""
        requirement = InterventionRequirement(
            **valid_requirement_kwargs,
            required_certification_codes=["DEAES"],
            required_skill_codes=["TOILETTE"],
        )
        assert requirement.requires_certifications() is True
        assert requirement.requires_skills() is True
        assert requirement.required_certification_codes == ["DEAES"]
        assert requirement.required_skill_codes == ["TOILETTE"]

    # ------------------------------------------------------------------ #
    #  InterventionTypeUpdateRequest — omitted against cleared
    # ------------------------------------------------------------------ #

    def test_an_omitted_requirement_is_not_sent(self) -> None:
        """Omitted means "leave them alone"."""
        payload = InterventionTypeUpdateRequest()
        assert payload.required_skill_codes is None
        assert "required_skill_codes" not in payload.model_dump(exclude_unset=True)

    def test_an_empty_requirement_is_sent(self) -> None:
        """An empty array means "require nothing from now on".

        Notes:
            This is the edit somebody makes after discovering that a skill
            requirement was stopping a service being planned at all.
        """
        payload = InterventionTypeUpdateRequest(required_skill_codes=[])
        assert payload.model_dump(exclude_unset=True) == {"required_skill_codes": []}

    def test_request_codes_are_normalised(self) -> None:
        """The same rule as the model it edits."""
        payload = InterventionTypeUpdateRequest(
            required_skill_codes=["toilette", "TOILETTE"]
        )
        assert payload.required_skill_codes == ["TOILETTE"]

    @pytest.mark.parametrize("invalid", ["TOILETTE", 42, [""], [42]])
    def test_a_malformed_request_requirement_is_refused(
        self, invalid: ModelInput
    ) -> None:
        """Refused on the way in, where the message can name the field."""
        with pytest.raises(MTInterventionTypeUpdateRequestInvalidSkills):
            InterventionTypeUpdateRequest(required_skill_codes=invalid)

    # ------------------------------------------------------------------ #
    #  Hca.holds_skills — who may take the work
    # ------------------------------------------------------------------ #

    def test_work_needing_nothing_is_satisfied_by_everybody(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An assistant with no declared skill can still take ungated work."""
        assistant = Hca(**valid_hca_kwargs)
        assert assistant.holds_skills([], date(2026, 8, 5)) is True

    def test_every_code_is_needed_not_any(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A requirement listing two skills means the person needs both.

        Notes:
            Reading it as "one of these" would send somebody to a visit
            half-qualified, which is the failure this field exists to prevent.
        """
        assistant = Hca(
            **valid_hca_kwargs,
            skills=[Skill(name="Toilette", code="TOILETTE")],
        )
        assert assistant.holds_skills(["TOILETTE"], date(2026, 8, 5)) is True
        assert assistant.holds_skills(["TOILETTE", "ARABE"], date(2026, 8, 5)) is False

    def test_an_uncoded_declaration_satisfies_nothing(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A free-text skill is a record, not a claim the planner can act on."""
        assistant = Hca(**valid_hca_kwargs, skills=[Skill(name="TOILETTE")])
        assert assistant.holds_skills(["TOILETTE"], date(2026, 8, 5)) is False

    def test_a_lapsed_declaration_does_not_qualify(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Judged on the day of the visit, not the day of the solve."""
        assistant = Hca(
            **valid_hca_kwargs,
            skills=[Skill(name="SST", code="SST", expires_on=date(2026, 6, 5))],
        )
        assert assistant.holds_skills(["SST"], date(2026, 6, 4)) is True
        assert assistant.holds_skills(["SST"], date(2026, 8, 5)) is False

    def test_skills_and_certifications_are_answered_separately(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The two lists do not satisfy each other.

        Notes:
            A single method taking both kinds of code would lose the one piece
            of information the answer is worth having for: which of the two a
            manager has to go and fix.
        """
        assistant = Hca(
            **valid_hca_kwargs,
            skills=[Skill(name="Toilette", code="TOILETTE")],
        )
        assert assistant.holds_skills(["TOILETTE"], date(2026, 8, 5)) is True
        assert assistant.holds_certifications(["TOILETTE"], date(2026, 8, 5)) is False

    def test_an_assistant_declares_nothing_by_default(
        self, valid_hca_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A row written before the table existed reads back as assignable."""
        assert Hca(**valid_hca_kwargs, skills=None).skills == []
