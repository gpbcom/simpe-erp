from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.catalog.exceptions import MTInterventionTypeInvalidRequiredCertifications
from models.catalog.intervention_type import InterventionType
from models.geo.geo_point import GeoPoint
from models.planning.intervention.exceptions import (
    MTRequirementInvalidRequiredCertifications,
)
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.quoting.exceptions import MTQuoteLineInvalidRequiredCertifications
from models.quoting.quote_line import QuoteLine
from models.schemas.exceptions import (
    MTInterventionTypeUpdateRequestInvalidCertifications,
)
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


class TestRequiredCertifications:
    """Tests for the certification requirement carried from catalogue to solver."""

    # ------------------------------------------------------------------ #
    #  InterventionType — the catalogue default
    # ------------------------------------------------------------------ #

    def test_a_catalogue_entry_requires_nothing_by_default(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Adding the field changed nothing about work already sold.

        Notes:
            A default that required something would have failed every planning
            run the moment it shipped — a migration failure wearing a solver's
            clothes.
        """
        assert InterventionType(**valid_type_kwargs).required_certification_codes == []

    def test_catalogue_codes_are_upper_cased(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Requirements and held qualifications must compare by equality."""
        entry = InterventionType(
            **valid_type_kwargs, required_certification_codes=["deaes", " sst "]
        )
        assert entry.required_certification_codes == ["DEAES", "SST"]

    def test_repeated_catalogue_codes_are_de_duplicated(
        self, valid_type_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The same code twice means what it means once.

        Notes:
            De-duplicated rather than refused: rejecting it would fail a save
            over something the screen can silently fix.
        """
        entry = InterventionType(
            **valid_type_kwargs, required_certification_codes=["DEAES", "deaes"]
        )
        assert entry.required_certification_codes == ["DEAES"]

    @pytest.mark.parametrize(
        "invalid_codes",
        [
            pytest.param("DEAES", id="Invalid - bare string"),
            pytest.param({"code": "DEAES"}, id="Invalid - mapping"),
            pytest.param(["DEAES", ""], id="Invalid - empty entry"),
            pytest.param(["DEAES", "  "], id="Invalid - blank entry"),
            pytest.param(["DEAES", 7], id="Invalid - int entry"),
            pytest.param([None], id="Invalid - None entry"),
        ],
    )
    def test_invalid_catalogue_codes_raise(
        self, valid_type_kwargs: Dict[str, ModelInput], invalid_codes: ModelInput
    ) -> None:
        """A malformed requirement is refused rather than dropped.

        Notes:
            Silently ignoring an entry would schedule an unqualified assistant
            on work the agency believed was gated.
        """
        with pytest.raises(MTInterventionTypeInvalidRequiredCertifications):
            InterventionType(
                **valid_type_kwargs, required_certification_codes=invalid_codes
            )

    # ------------------------------------------------------------------ #
    #  QuoteLine — the three states
    # ------------------------------------------------------------------ #

    def test_a_line_inherits_the_catalogue_by_default(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """``None`` means "whatever the catalogue entry requires"."""
        line = QuoteLine(**valid_line_kwargs)
        assert line.required_certification_codes is None
        assert line.effective_certification_codes(["DEAES"]) == ["DEAES"]

    def test_a_line_override_replaces_the_catalogue(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A list means "these, instead of the catalogue's"."""
        line = QuoteLine(**valid_line_kwargs, required_certification_codes=["sst"])
        assert line.effective_certification_codes(["DEAES"]) == ["SST"]

    def test_an_empty_override_requires_nothing(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """An empty list means "this hour needs no qualification at all".

        Notes:
            This is the state that makes the field nullable rather than a plain
            list. Collapsing ``None`` and ``[]`` would silently reinstate a
            requirement the person writing the quote had deliberately removed.
        """
        line = QuoteLine(**valid_line_kwargs, required_certification_codes=[])
        assert line.required_certification_codes == []
        assert line.effective_certification_codes(["DEAES"]) == []

    def test_the_resolved_list_is_a_copy(
        self, valid_line_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Mutating the answer must not edit the catalogue entry it came from.

        Notes:
            The requirement builder resolves one list per line against a single
            shared catalogue entry, so handing back the entry's own list would
            let one line's edit reach every other line selling the same
            service.
        """
        catalogue = ["DEAES"]
        resolved = QuoteLine(**valid_line_kwargs).effective_certification_codes(
            catalogue
        )
        resolved.append("SST")
        assert catalogue == ["DEAES"]

    @pytest.mark.parametrize(
        "invalid_codes",
        [
            pytest.param("DEAES", id="Invalid - bare string"),
            pytest.param(["DEAES", ""], id="Invalid - empty entry"),
            pytest.param([7], id="Invalid - int entry"),
        ],
    )
    def test_invalid_line_codes_raise(
        self, valid_line_kwargs: Dict[str, ModelInput], invalid_codes: ModelInput
    ) -> None:
        """A malformed override is refused."""
        with pytest.raises(MTQuoteLineInvalidRequiredCertifications):
            QuoteLine(**valid_line_kwargs, required_certification_codes=invalid_codes)

    # ------------------------------------------------------------------ #
    #  InterventionRequirement — what the solver reads
    # ------------------------------------------------------------------ #

    def test_a_requirement_needs_nothing_by_default(
        self, valid_requirement_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Most work needs no qualification, and that is the cheap path."""
        requirement = InterventionRequirement(**valid_requirement_kwargs)
        assert requirement.required_certification_codes == []
        assert requirement.requires_certifications() is False

    def test_a_requirement_reports_when_it_needs_something(
        self, valid_requirement_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The solver skips the whole constraint when nothing is required."""
        requirement = InterventionRequirement(
            **valid_requirement_kwargs, required_certification_codes=["DEAES"]
        )
        assert requirement.requires_certifications() is True

    def test_requirement_codes_are_normalised_again(
        self, valid_requirement_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A requirement built directly still reaches the solver comparable.

        Notes:
            The builder already upper-cases, but a requirement is also built in
            tests and could be built by a future caller. A code in the wrong
            case would match nobody and fail the run with a reason that looks
            like a staffing problem.
        """
        requirement = InterventionRequirement(
            **valid_requirement_kwargs,
            required_certification_codes=["deaes", "DEAES", " sst "],
        )
        assert requirement.required_certification_codes == ["DEAES", "SST"]

    @pytest.mark.parametrize(
        "invalid_codes",
        [
            pytest.param("DEAES", id="Invalid - bare string"),
            pytest.param([""], id="Invalid - empty entry"),
            pytest.param([7], id="Invalid - int entry"),
        ],
    )
    def test_invalid_requirement_codes_raise(
        self, valid_requirement_kwargs: Dict[str, ModelInput], invalid_codes: ModelInput
    ) -> None:
        """A malformed requirement never reaches the solver."""
        with pytest.raises(MTRequirementInvalidRequiredCertifications):
            InterventionRequirement(
                **valid_requirement_kwargs,
                required_certification_codes=invalid_codes,
            )

    # ------------------------------------------------------------------ #
    #  InterventionTypeUpdateRequest — sent, cleared, or omitted
    # ------------------------------------------------------------------ #

    def test_an_omitted_requirement_is_left_alone(self) -> None:
        """``None`` means "not sent", which the route drops with exclude_unset."""
        payload = InterventionTypeUpdateRequest(name="Soin")
        assert payload.required_certification_codes is None
        assert "required_certification_codes" not in payload.model_dump(
            exclude_unset=True
        )

    def test_an_empty_requirement_clears_it(self) -> None:
        """An empty list is the edit somebody makes when a requirement was wrong.

        Notes:
            Collapsing it into "not sent" would make a requirement impossible
            to lift once one had been set.
        """
        payload = InterventionTypeUpdateRequest(required_certification_codes=[])
        assert payload.model_dump(exclude_unset=True) == {
            "required_certification_codes": []
        }

    def test_requested_codes_are_normalised(self) -> None:
        """The wire form is normalised before it reaches the catalogue entry."""
        payload = InterventionTypeUpdateRequest(
            required_certification_codes=["deaes", "DEAES"]
        )
        assert payload.required_certification_codes == ["DEAES"]

    @pytest.mark.parametrize(
        "invalid_codes",
        [
            pytest.param("DEAES", id="Invalid - bare string"),
            pytest.param([""], id="Invalid - empty entry"),
            pytest.param([7], id="Invalid - int entry"),
        ],
    )
    def test_invalid_requested_codes_raise(self, invalid_codes: ModelInput) -> None:
        """A malformed payload is refused with a message naming the field."""
        with pytest.raises(MTInterventionTypeUpdateRequestInvalidCertifications):
            InterventionTypeUpdateRequest(required_certification_codes=invalid_codes)
