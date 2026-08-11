from __future__ import annotations

# Standard library imports
from datetime import timedelta
from typing import Dict, List

# Third-party imports
import pytest

# First-party imports
from models.people.hca.skill import Skill
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.planning.planning_run.planning_solution import ScheduledAssignment
from service.planning.slot_finder import SlotFinder

# Local imports
from tests.planning_scenarios.builder import ScenarioBuilder

MONDAY = ScenarioBuilder.MONDAY
TUESDAY = MONDAY + timedelta(days=1)


@pytest.fixture
def build() -> ScenarioBuilder:
    """Return the shared fixture builder.

    Returns:
        ScenarioBuilder: Realistic defaults for assistants and work.
    """
    return ScenarioBuilder()


def _index(
    requirements: List[InterventionRequirement],
) -> Dict[str, InterventionRequirement]:
    """Return the work by identifier.

    Args:
        requirements (List[InterventionRequirement]): The work.

    Returns:
        Dict[str, InterventionRequirement]: The same work, keyed by id.
    """
    return {item.id: item for item in requirements}


class TestOfferingAnAlternative:
    """Tests for the times offered when a visit could not be placed.

    Notes:
        The point of these offers is that an operator telephoning a customer
        has something to propose. So what matters is that a slot is genuinely
        free at the moment it is offered — a suggestion that turns out not to
        fit is worse than no suggestion, because it costs a second call.
    """

    def test_an_empty_week_offers_the_start_of_the_day(
        self, build: ScenarioBuilder
    ) -> None:
        """With nothing booked, the first free time is the day's own start.

        Args:
            build (ScenarioBuilder): The fixture builder.
        """
        work = build.requirement("req-1")
        finder = SlotFinder(build.settings())

        slots = finder.find(work, [build.assistant()], [], _index([work]), [MONDAY])

        assert slots
        assert slots[0].start_minute == build.settings().day_start_minute

    def test_a_booked_morning_pushes_the_offer_later(
        self, build: ScenarioBuilder
    ) -> None:
        """The gap after an existing visit is where the work can go.

        Args:
            build (ScenarioBuilder): The fixture builder.
        """
        booked = build.requirement("req-booked")
        wanted = build.requirement("req-1")
        assignments = [
            ScheduledAssignment(
                requirement_id="req-booked",
                hca_id="hca-1",
                start_minute=9 * 60,
                end_minute=11 * 60,
            )
        ]
        finder = SlotFinder(build.settings())

        slots = finder.find(
            wanted,
            [build.assistant("hca-1")],
            assignments,
            _index([booked, wanted]),
            [MONDAY],
        )

        assert slots
        assert slots[0].start_minute >= 11 * 60

    def test_the_lunch_break_is_never_offered(self, build: ScenarioBuilder) -> None:
        """An hour the assistant must eat in is not an hour they are free.

        Args:
            build (ScenarioBuilder): The fixture builder.

        Notes:
            The break is not pinned to an hour in the model — the solver
            places it — so the whole configured window is treated as taken.
            That can only withhold a usable slot, never offer an unusable one.
        """
        settings = build.settings()
        work = build.requirement("req-1")
        finder = SlotFinder(settings)

        slots = finder.find(work, [build.assistant()], [], _index([work]), [MONDAY])

        for slot in slots:
            overlaps = (
                slot.start_minute < settings.lunch_window_end_minute
                and slot.end_minute > settings.lunch_window_start_minute
            )
            assert not overlaps

    def test_nobody_qualified_means_nothing_is_offered(
        self, build: ScenarioBuilder
    ) -> None:
        """A free hour with the wrong person is not an alternative.

        Args:
            build (ScenarioBuilder): The fixture builder.

        Notes:
            The one failure mode worth guarding hardest. Offering a slot the
            next planning run will refuse sends an operator to renegotiate a
            date that was never available.
        """
        work = build.requirement("req-1", skill_codes=["LEVE-PERSONNE"])
        finder = SlotFinder(build.settings())

        slots = finder.find(work, [build.assistant()], [], _index([work]), [MONDAY])

        assert slots == []

    def test_the_qualified_assistant_is_the_one_offered(
        self, build: ScenarioBuilder
    ) -> None:
        """The gate selects as well as excluding.

        Args:
            build (ScenarioBuilder): The fixture builder.
        """
        work = build.requirement("req-1", skill_codes=["CUISINE"])
        able = build.assistant("hca-2", skills=[Skill(name="C", code="CUISINE")])
        finder = SlotFinder(build.settings())

        slots = finder.find(
            work,
            [build.assistant("hca-1"), able],
            [],
            _index([work]),
            [MONDAY],
        )

        assert slots
        assert all(slot.hca_id == "hca-2" for slot in slots)

    def test_a_day_off_is_not_offered(self, build: ScenarioBuilder) -> None:
        """Somebody who does not work Monday is not free on Monday.

        Args:
            build (ScenarioBuilder): The fixture builder.
        """
        work = build.requirement("req-1", day=MONDAY)
        away = build.assistant(availability=[build.absence("hca-1", MONDAY)])
        finder = SlotFinder(build.settings())

        slots = finder.find(work, [away], [], _index([work]), [MONDAY])

        assert slots == []

    def test_later_days_are_searched_when_the_first_is_full(
        self, build: ScenarioBuilder
    ) -> None:
        """A week is looked at, not just the day the visit wanted.

        Args:
            build (ScenarioBuilder): The fixture builder.
        """
        settings = build.settings()
        work = build.requirement("req-1")
        # Monday booked solid from the start of the day to the end.
        assignments = [
            ScheduledAssignment(
                requirement_id="req-full",
                hca_id="hca-1",
                start_minute=settings.day_start_minute,
                end_minute=settings.day_end_minute,
            )
        ]
        full = build.requirement("req-full", day=MONDAY)
        finder = SlotFinder(settings)

        slots = finder.find(
            work,
            [build.assistant("hca-1")],
            assignments,
            _index([work, full]),
            [MONDAY, TUESDAY],
        )

        assert slots
        assert all(slot.day == TUESDAY for slot in slots)

    def test_the_number_of_offers_is_capped(self, build: ScenarioBuilder) -> None:
        """Twenty options is a second problem, not a choice.

        Args:
            build (ScenarioBuilder): The fixture builder.
        """
        work = build.requirement("req-1")
        staff = [build.assistant(f"hca-{index}") for index in range(8)]
        finder = SlotFinder(build.settings())

        slots = finder.find(work, staff, [], _index([work]), [MONDAY, TUESDAY], limit=3)

        assert len(slots) <= 3

    def test_an_offer_is_long_enough_for_the_work(self, build: ScenarioBuilder) -> None:
        """A slot shorter than the service is not a slot for it.

        Args:
            build (ScenarioBuilder): The fixture builder.
        """
        work = build.requirement("req-1", duration_minutes=90)
        finder = SlotFinder(build.settings())

        slots = finder.find(work, [build.assistant()], [], _index([work]), [MONDAY])

        assert slots
        assert all(slot.duration_minutes() >= 90 for slot in slots)
