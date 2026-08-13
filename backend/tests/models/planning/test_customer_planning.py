from __future__ import annotations

# Standard library imports
from datetime import date, datetime, time
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.enums import InterventionStatus
from models.planning.customer_planning import CustomerPlanning
from models.planning.customer_planning.exceptions import (
    MTCustomerPlanningInvalidCustomerId,
    MTCustomerPlanningInvalidCustomerName,
    MTCustomerPlanningInvalidInterventions,
    MTCustomerPlanningInvalidPeriod,
    MTInvalidCustomerPlanningException,
)
from models.planning.intervention import Intervention
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


def _visit(
    visit_id: str = "visit-1",
    day: date = MONDAY,
    start: time = time(9, 0),
    hca_full_name: str = "Luc Martin",
) -> Intervention:
    """Build a visit delivered to the household.

    Args:
        visit_id (str): The identifier to assign.
        day (date): The day it happens.
        start (time): When it begins.
        hca_full_name (str): Who delivers it.

    Returns:
        Intervention: The visit.
    """
    return Intervention(
        company_id="company-1",
        team_id="team-1",
        id=visit_id,
        planning_run_id="run-1",
        name="Toilette matin",
        intervention_type_id="type-1",
        quote_line_id="line-1",
        hca_id="hca-1",
        hca_full_name=hca_full_name,
        customer_id="customer-1",
        day=day,
        start_time=start,
        end_time=time(start.hour + 1, 0),
        address=ADDRESS,
        status=InterventionStatus.PLANNED,
    )


@pytest.fixture
def valid_kwargs() -> Dict[str, ModelInput]:
    """Return the keyword arguments for a valid planning.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {
        "customer_id": "customer-1",
        "customer_full_name": "Marie Durand",
        "period_start": MONDAY,
        "period_end": SUNDAY,
    }


class TestCustomerPlanning:
    """Tests for one household's care over a period."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_period_with_no_care_is_valid(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """A household between arrangements has an empty week, not an error."""
        planning = CustomerPlanning(**valid_kwargs)

        assert planning.interventions == []
        assert planning.total_minutes() == 0
        assert planning.by_day() == {}

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - missing"),
            pytest.param(42, id="Invalid - not a string"),
        ],
    )
    def test_an_unusable_customer_id_is_refused(
        self, valid_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """The identifier is what the visits were read by."""
        with pytest.raises(MTCustomerPlanningInvalidCustomerId):
            CustomerPlanning(**{**valid_kwargs, "customer_id": value})

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - missing"),
        ],
    )
    def test_an_unnamed_household_is_refused(
        self, valid_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """**The name is why this envelope exists.**

        Notes:
            A visit carries the assistant's name but only the household's
            identifier. A rail printing UUIDs beside a week of care is one
            nobody can read, so a planning without a name is not worth building.
        """
        with pytest.raises(MTCustomerPlanningInvalidCustomerName):
            CustomerPlanning(**{**valid_kwargs, "customer_full_name": value})

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param("period_start", id="The first day"),
            pytest.param("period_end", id="The last day"),
        ],
    )
    def test_a_period_bound_that_is_not_a_date_is_refused(
        self, valid_kwargs: Dict[str, ModelInput], field: str
    ) -> None:
        """A window nobody can compute is one nothing can be read over."""
        with pytest.raises(MTCustomerPlanningInvalidPeriod):
            CustomerPlanning(**{**valid_kwargs, field: 1234567890})

    def test_a_datetime_bound_is_reduced_to_its_day(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The window is days, so a timestamp keeps only its date."""
        planning = CustomerPlanning(
            **{**valid_kwargs, "period_start": datetime(2026, 8, 3, 14, 30)}
        )

        assert planning.period_start == MONDAY

    def test_a_backwards_period_is_refused(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Both bounds are inclusive, so only a reversed window is wrong."""
        with pytest.raises(MTCustomerPlanningInvalidPeriod):
            CustomerPlanning(
                **{**valid_kwargs, "period_start": SUNDAY, "period_end": MONDAY}
            )

    def test_a_single_day_period_is_valid(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """Somebody asking about today is asking a legitimate question."""
        planning = CustomerPlanning(
            **{**valid_kwargs, "period_start": MONDAY, "period_end": MONDAY}
        )

        assert planning.period_start == planning.period_end

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("visit-1", id="Invalid - a bare string"),
            pytest.param(["visit-1"], id="Invalid - a list of strings"),
        ],
    )
    def test_unusable_interventions_are_refused(
        self, valid_kwargs: Dict[str, ModelInput], value: ModelInput
    ) -> None:
        """A list of identifiers is not a list of visits."""
        with pytest.raises(MTCustomerPlanningInvalidInterventions):
            CustomerPlanning(**{**valid_kwargs, "interventions": value})

    def test_absent_interventions_read_as_none_at_all(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """``None`` is an empty week, not a missing field."""
        planning = CustomerPlanning(**{**valid_kwargs, "interventions": None})

        assert planning.interventions == []

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    def test_the_care_is_grouped_by_day_in_time_order(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """The shape a calendar draws from, and a family reads their week in."""
        planning = CustomerPlanning(
            **{
                **valid_kwargs,
                "interventions": [
                    _visit("afternoon", start=time(14, 0)),
                    _visit("morning", start=time(9, 0)),
                    _visit("other-day", day=date(2026, 8, 5)),
                ],
            }
        )

        grouped = planning.by_day()

        assert [visit.id for visit in grouped[MONDAY]] == ["morning", "afternoon"]
        assert [visit.id for visit in grouped[date(2026, 8, 5)]] == ["other-day"]

    def test_the_total_is_every_visit_added_up(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """How much care the household receives, in minutes."""
        planning = CustomerPlanning(
            **{
                **valid_kwargs,
                "interventions": [_visit("one"), _visit("two", start=time(14, 0))],
            }
        )

        assert planning.total_minutes() == 120

    def test_the_assistants_are_named_once_each(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """**The question a family actually rings about.**

        Notes:
            Answered from the names already copied onto each visit, so it needs
            no second read and survives the assistant leaving the agency.
        """
        planning = CustomerPlanning(
            **{
                **valid_kwargs,
                "interventions": [
                    _visit("one", hca_full_name="Luc Martin"),
                    _visit("two", start=time(11, 0), hca_full_name="Amina Benali"),
                    _visit("three", start=time(14, 0), hca_full_name="Luc Martin"),
                ],
            }
        )

        assert planning.assistants() == ["Amina Benali", "Luc Martin"]

    def test_two_assistants_at_once_is_not_reported_as_a_clash(
        self, valid_kwargs: Dict[str, ModelInput]
    ) -> None:
        """**Why this model has no ``overlapping_pairs``.**

        Notes:
            On an assistant's diary an overlap is *the* error — one person
            cannot be in two homes. A household may legitimately have two
            assistants at the same hour, for a transfer that takes two people.
            A method reporting that as a clash would invent a rule the agency
            does not have, so there is none to call.
        """
        planning = CustomerPlanning(
            **{
                **valid_kwargs,
                "interventions": [
                    _visit("one", hca_full_name="Luc Martin"),
                    _visit("two", hca_full_name="Amina Benali"),
                ],
            }
        )

        assert not hasattr(planning, "overlapping_pairs")
        assert len(planning.by_day()[MONDAY]) == 2

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTCustomerPlanningInvalidCustomerId,
            MTCustomerPlanningInvalidCustomerName,
            MTCustomerPlanningInvalidInterventions,
            MTCustomerPlanningInvalidPeriod,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """The family the API maps; the members are reached through the MRO."""
        assert issubclass(exception_class, MTInvalidCustomerPlanningException)
