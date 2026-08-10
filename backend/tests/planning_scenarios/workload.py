from __future__ import annotations

from datetime import date, timedelta

# Standard library imports
import math
from typing import ClassVar, Dict, List, Optional, Tuple

# First-party imports
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.people.hca.certification import Certification
from models.people.hca.skill import Skill
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)

# Local imports
from tests.planning_scenarios.builder import ScenarioBuilder


class WorkloadGenerator:
    """Builds week-sized planning instances that are solvable by construction.

    Attributes:
        build (ScenarioBuilder): Supplies the realistic defaults.

    Notes:
        - **The instance is derived from a known-good schedule, not invented and
          then hoped over.** A round is laid down first — assistant by assistant,
          day by day, leaving room for travel and the lunch break — and each
          requirement is then read back off the slot it was placed in. A feasible
          plan therefore provably exists, so "the solver left work unplaced" is
          always a finding about the solver and never an artefact of the
          generator.
        - That distinction is the whole reason this class exists. Two instances
          hand-built earlier in this work were used to size a solver budget and
          both were wrong: one gave every visit the full working day as its
          window and was far harder than any real week, the other was
          over-constrained and left 28 of 95 visits genuinely unplaceable. Both
          looked reasonable.
        - Realism is kept by **snapping each window to one of the agency's own
          service windows** whenever the placed slot fits inside one. Wide
          windows are what made the first bad instance intractable, so a
          generator that guaranteed feasibility by making every window enormous
          would have swapped one unrealistic instance for another.
        - Qualifications are derived the same way: a visit that requires a skill
          requires one its scheduled assistant actually holds. Requiring a
          random skill would make the instance infeasible for a reason that has
          nothing to do with what is being measured.
    """

    #: The licensed travel speed, matching ``PlanningConfig.average_speed_kmh``.
    SPEED_KMH: ClassVar[float] = 30.0

    #: Which of the agency's service windows a round may use, in order.
    #:
    #: Window 2 (11:30-14:00) is deliberately left out. The lunch break is an
    #: uninterrupted hour that must fall between 11:30 and 14:30, so a round
    #: working through that window has nowhere to put it, and the solver would
    #: refuse the very schedule this class promises is feasible.
    ROUND_WINDOWS: ClassVar[Tuple[int, ...]] = (0, 1, 3, 4)

    SKILL_CODES: ClassVar[Tuple[str, ...]] = ("LEVE-PERSONNE", "CUISINE", "ARABE")
    CERTIFICATION_CODES: ClassVar[Tuple[str, ...]] = ("DEAES", "DEAVS", "ADVF")

    def __init__(self) -> None:
        """Initialize the generator over a shared builder."""
        self.build = ScenarioBuilder()

    ############################
    # Internal Helpers Methods #
    ############################

    def _home_of(self, index: int) -> GeoPoint:
        """Return where one assistant lives.

        Args:
            index (int): Which assistant.

        Returns:
            GeoPoint: A home spread across central Paris.

        Notes:
            Spread deliberately, so the radius and the travel objective both
            have something to bite on. Twelve assistants sharing one address
            would make every route free and every measurement meaningless.
        """
        return GeoPoint(
            latitude=ScenarioBuilder.HOME.latitude + (index % 4) * 0.020,
            longitude=ScenarioBuilder.HOME.longitude + (index % 3) * 0.028,
        )

    def _visit_point(self, index: int) -> GeoPoint:
        """Return where one visit happens.

        Args:
            index (int): Which visit in the week.

        Returns:
            GeoPoint: A point on a grid across the city.

        Notes:
            - **Independent of who was scheduled to do it, and that is the
              point.** An earlier version placed every visit near its own
              assistant's home, and the instance it produced was far too easy:
              ninety-five visits solved to proven optimality in twelve seconds,
              where the real week of the same size runs for tens of minutes and
              comes back one short. Clustering had quietly given nearly every
              visit one obvious taker.
            - Real customers are spread across the city and most visits could
              plausibly go to any of several assistants. That symmetry is what
              makes the search large, so a generator that removes it measures
              a problem the agency does not have.
            - Feasibility is preserved instead by advancing the schedule's
              cursor by the **real** travel time between consecutive points —
              see :meth:`_travel_minutes` — rather than by assuming a fixed
              allowance that clustering happened to satisfy.
        """
        return GeoPoint(
            latitude=ScenarioBuilder.HOME.latitude + ((index % 7) - 3) * 0.013,
            longitude=ScenarioBuilder.HOME.longitude + ((index % 5) - 2) * 0.019,  # noqa: E501
        )

    def _travel_minutes(self, origin: GeoPoint, destination: GeoPoint) -> int:
        """Return the drive between two points, as the solver will charge it.

        Args:
            origin (GeoPoint): Where the assistant is.
            destination (GeoPoint): Where they are going.

        Returns:
            int: Minutes, rounded up.

        Notes:
            Deliberately the same arithmetic as
            ``PlanningService._estimate_minutes``: straight-line distance at
            the licensed speed, rounded up. If the generator were more
            optimistic than the solver by even a minute, the schedule it lays
            down would not be one the solver can reproduce, and the promise
            that a feasible plan exists would be false.
        """
        return math.ceil(origin.distance_km(destination) / self.SPEED_KMH * 60)

    def _skills_of(self, index: int) -> List[Skill]:
        """Return the skills one assistant has declared.

        Args:
            index (int): Which assistant.

        Returns:
            List[Skill]: A deterministic subset of :attr:`SKILL_CODES`.
        """
        return [
            Skill(name=code.title(), code=code)
            for position, code in enumerate(self.SKILL_CODES)
            if (index + position) % 3 == 0
        ]

    def _certifications_of(self, index: int) -> List[Certification]:
        """Return the qualifications one assistant holds.

        Args:
            index (int): Which assistant.

        Returns:
            List[Certification]: A deterministic subset of the codes.
        """
        return [
            Certification(name=code, code=code)
            for position, code in enumerate(self.CERTIFICATION_CODES)
            if (index + position) % 2 == 0
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def workforce(self, assistants: int) -> List[Hca]:
        """Build the agency's field staff.

        Args:
            assistants (int): How many to build.

        Returns:
            List[Hca]: The workforce, spread across Paris and unevenly
            qualified.
        """
        return [
            self.build.assistant(
                hca_id=f"hca-{index}",
                skills=self._skills_of(index),
                certifications=self._certifications_of(index),
                home=self._home_of(index),
            )
            for index in range(assistants)
        ]

    def week(
        self,
        staff: List[Hca],
        visits: int,
        days: int = 5,
        gated_every: Optional[int] = 4,
    ) -> List[InterventionRequirement]:
        """Build a week of work that the given workforce can certainly do.

        Args:
            staff (List[Hca]): The workforce the schedule is laid down over.
            visits (int): How many visits to produce.
            days (int): How many consecutive days to spread them across.
            gated_every (Optional[int]): One visit in this many requires a
                qualification. ``None`` gates nothing.

        Returns:
            List[InterventionRequirement]: The work, in a stable order.

        Notes:
            - Rounds are filled breadth-first — one visit each to every
              assistant-day before any of them takes a second — because a real
              agency spreads its work rather than exhausting one person's
              Monday before touching anybody else's.
            - Each visit takes the next of :attr:`ROUND_WINDOWS` in its round, so
              a round runs chronologically and every window is one the agency
              actually offers. The cursor then advances by the **real** drive
              between the two points, which is what keeps the schedule one the
              solver can reproduce.
            - A visit that will not fit its window is dropped rather than forced.
              Returning fewer visits than asked is honest; returning a visit the
              round cannot reach would break the guarantee the whole class rests
              on.
        """
        cursors: Dict[Tuple[str, int], int] = {}
        previous: Dict[Tuple[str, int], GeoPoint] = {}
        sequences: Dict[Tuple[str, int], int] = {}
        requirements: List[InterventionRequirement] = []
        settings = self.build.settings()
        rounds = len(staff) * days

        for index in range(visits):
            assistant = staff[index % len(staff)]
            offset = (index // len(staff)) % days
            key = (assistant.id or f"hca-{index}", offset)
            slot = index // rounds
            if slot >= len(self.ROUND_WINDOWS):
                continue

            window_start, window_end, duration = ScenarioBuilder.WINDOWS[
                self.ROUND_WINDOWS[slot]
            ]
            location = self._visit_point(index)
            cursor = cursors.get(key, settings.day_start_minute)
            travel = (
                0
                if key not in previous
                else self._travel_minutes(previous[key], location)
            )
            start = max(window_start, cursor + travel)
            end = start + duration
            if end > window_end or end > settings.day_end_minute:
                continue

            gated = gated_every is not None and index % gated_every == 0
            codes = [held.code for held in assistant.skills if held.code]
            requirements.append(
                InterventionRequirement(
                    id=f"req-{index}",
                    quote_line_id=f"line-{index}",
                    customer_id=f"customer-{index}",
                    name="Aide a la toilette",
                    intervention_type_id="type-1",
                    day=ScenarioBuilder.MONDAY + timedelta(days=offset),
                    window_start_minute=window_start,
                    window_end_minute=window_end,
                    duration_minutes=duration,
                    location=location,
                    required_skill_codes=codes[:1] if gated and codes else [],
                )
            )
            cursors[key] = end
            previous[key] = location
            sequences[key] = sequences.get(key, 0) + 1
        return requirements

    def day_count(self, requirements: List[InterventionRequirement]) -> int:
        """Return how many distinct days the work falls on.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Returns:
            int: The number of days, which is the number of models a per-day
            solve will build.
        """
        return len({requirement.day for requirement in requirements})

    def busiest_day(
        self, requirements: List[InterventionRequirement]
    ) -> Tuple[Optional[date], int]:
        """Return the day carrying the most work, and how much.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Returns:
            Tuple[Optional[date], int]: The day and its count, or
            ``(None, 0)`` when there is no work.

        Notes:
            Under a per-day decomposition the wall clock is the slowest single
            day rather than the sum, so this is the figure that predicts it.
        """
        counts: Dict[date, int] = {}
        for requirement in requirements:
            counts[requirement.day] = counts.get(requirement.day, 0) + 1
        if not counts:
            return None, 0
        day = max(sorted(counts), key=lambda entry: counts[entry])
        return day, counts[day]
