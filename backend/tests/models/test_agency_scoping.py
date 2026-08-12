from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import Dict

# Third-party imports
import pytest
from pydantic import ValidationError

# First-party imports
from models.planning.intervention import Intervention
from models.planning.intervention.exceptions import MTInterventionInvalidId
from models.planning.planning_run import PlanningRun
from models.planning.planning_run.exceptions import MTPlanningRunInvalidId
from models.quoting.exceptions import MTQuoteInvalidId
from models.quoting.quote import Quote
from tests.annotations import ModelInput

MONDAY = date(2026, 8, 3)
SUNDAY = date(2026, 8, 9)

ADDRESS: Dict[str, ModelInput] = {
    "street": "12 rue de Rivoli",
    "postal_code": "75004",
    "city": "Paris",
    "latitude": 48.8566,
    "longitude": 2.3522,
}


def _quote(**overrides: ModelInput) -> Quote:
    """Build a quote, overriding whatever a test is about.

    Args:
        **overrides: Fields to replace.

    Returns:
        Quote: The quote.
    """
    fields: Dict[str, ModelInput] = {
        "company_id": "company-1",
        "reference": "D-2601",
        "customer_id": "customer-1",
    }
    fields.update(overrides)
    return Quote(**fields)


def _run(**overrides: ModelInput) -> PlanningRun:
    """Build a planning run, overriding whatever a test is about.

    Args:
        **overrides: Fields to replace.

    Returns:
        PlanningRun: The run.
    """
    fields: Dict[str, ModelInput] = {
        "company_id": "company-1",
        "requested_by": "admin-1",
        "period_start": MONDAY,
        "period_end": SUNDAY,
    }
    fields.update(overrides)
    return PlanningRun(**fields)


def _visit(**overrides: ModelInput) -> Intervention:
    """Build a scheduled visit, overriding whatever a test is about.

    Args:
        **overrides: Fields to replace.

    Returns:
        Intervention: The visit.
    """
    fields: Dict[str, ModelInput] = {
        "company_id": "company-1",
        "name": "Toilette matin",
        "intervention_type_id": "type-1",
        "quote_line_id": "line-1",
        "hca_id": "hca-1",
        "hca_full_name": "Luc Martin",
        "customer_id": "customer-1",
        "day": MONDAY,
        "start_time": time(9, 0),
        "end_time": time(11, 0),
        "address": ADDRESS,
    }
    fields.update(overrides)
    return Intervention(**fields)


class TestEveryPlannedRecordNamesItsAgency:
    """Tests for the rule the planning computation is scoped by.

    Notes:
        **These three models are the ones the solver reads and writes**, and
        until each carried an agency the computation had no way to tell whose
        work it was scheduling. A run selected every agency's accepted quotes
        and then deleted and rewrote every agency's visits in its period, so two
        agencies planning overlapping weeks — which the per-agency queues make
        the normal case, not a rare race — lost each other's calendars.

        The field is therefore required rather than optional on all three. What
        makes the scoping a property rather than a discipline is that there is
        no state in which one of these records exists without naming an agency.
    """

    # ------------------------------------------------------------------ #
    #  Required, on all three
    # ------------------------------------------------------------------ #

    def test_a_quote_must_name_its_agency(self) -> None:
        """A quote with no agency cannot be built at all.

        Notes:
            ``ValidationError`` rather than the model's own ``MT*``: a field
            that was never sent has no value for a before-validator to inspect,
            so Pydantic refuses it before the validator is reached. The custom
            exceptions below cover the values that *are* sent and are unusable.
            Both answer 422, which is what a caller sees either way.
        """
        with pytest.raises(ValidationError):
            Quote(reference="D-2601", customer_id="customer-1")

    def test_a_run_must_name_its_agency(self) -> None:
        """A run with no agency cannot be built at all."""
        with pytest.raises(ValidationError):
            PlanningRun(requested_by="admin-1", period_start=MONDAY, period_end=SUNDAY)

    def test_a_visit_must_name_its_agency(self) -> None:
        """A visit with no agency cannot be built at all."""
        with pytest.raises(ValidationError):
            Intervention(
                name="Toilette matin",
                intervention_type_id="type-1",
                quote_line_id="line-1",
                hca_id="hca-1",
                hca_full_name="Luc Martin",
                customer_id="customer-1",
                day=MONDAY,
                start_time=time(9, 0),
                end_time=time(11, 0),
                address=ADDRESS,
            )

    # ------------------------------------------------------------------ #
    #  Not satisfied by something that merely looks present
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_company",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
            pytest.param(["company-1"], id="Invalid - list"),
        ],
    )
    def test_a_quote_refuses_an_unusable_agency(
        self, invalid_company: ModelInput
    ) -> None:
        """Blank is not an agency, and neither is a list holding one.

        Notes:
            A blank would pass a truthiness check and then match no agency's
            rows, which reads as an agency with no accepted work rather than as
            a broken quote — the quiet failure this refuses to allow.
        """
        with pytest.raises(MTQuoteInvalidId):
            _quote(company_id=invalid_company)

    @pytest.mark.parametrize(
        "invalid_company",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_a_run_refuses_an_unusable_agency(
        self, invalid_company: ModelInput
    ) -> None:
        """A run that named nothing would clear a period and fill it with nothing."""
        with pytest.raises(MTPlanningRunInvalidId):
            _run(company_id=invalid_company)

    @pytest.mark.parametrize(
        "invalid_company",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_a_visit_refuses_an_unusable_agency(
        self, invalid_company: ModelInput
    ) -> None:
        """A visit is deleted in bulk by its agency and day."""
        with pytest.raises(MTInterventionInvalidId):
            _visit(company_id=invalid_company)

    # ------------------------------------------------------------------ #
    #  Normalisation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "build",
        [
            pytest.param(_quote, id="Quote"),
            pytest.param(_run, id="PlanningRun"),
            pytest.param(_visit, id="Intervention"),
        ],
    )
    def test_the_agency_is_stripped(self, build: ModelInput) -> None:
        """Surrounding whitespace is removed on all three.

        Notes:
            They are compared with ``==`` in the queries that scope the
            computation, so ``" company-1"`` and ``"company-1"`` would be two
            agencies as far as the planner is concerned.
        """
        assert build(company_id="  company-1  ").company_id == "company-1"

    # ------------------------------------------------------------------ #
    #  The run's agency does not come from the requester
    # ------------------------------------------------------------------ #

    def test_a_run_keeps_its_agency_independently_of_who_asked(self) -> None:
        """The requester and the agency are separate facts.

        Notes:
            ``requested_by`` carries no foreign key, so the administrator who
            asked for a run is allowed to be gone by the time a worker picks it
            up. Deriving the agency from them at that point would leave the run
            unexecutable; recording it here is what survives their departure.
        """
        run = _run(company_id="company-2", requested_by="admin-1")

        assert run.company_id == "company-2"
        assert run.requested_by == "admin-1"

    def test_a_quote_keeps_its_agency_without_an_author(self) -> None:
        """``authored_by`` is optional; the agency is not.

        Notes:
            This is the pair that made the field necessary. The agency used to
            be reachable only through the author's account, and an author who
            leaves takes that path with them — leaving a quote the planner could
            not attribute, which it would then schedule for whichever agency ran
            next.
        """
        quote = _quote(authored_by=None)

        assert quote.company_id == "company-1"
        assert quote.authored_by is None
