from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import Dict, List, Optional, Tuple

# First-party imports
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.planning.planning_run.planning_solution import ScheduledAssignment
from models.planning.planning_run.suggested_slot import SuggestedSlot
from models.settings.planning_settings import PlanningSettings


class SlotFinder:
    """Finds times a qualified assistant is free, for work that would not fit.

    Attributes:
        settings (PlanningSettings): The working day and break rules.
        logger (Logger): Logger for slot searching.

    Notes:
        - **This answers the question an operator asks next.** Being told that a
          visit could not be placed leaves them to telephone the customer with
          nothing to propose; being told "Wednesday at 14:00 with Amina Benali,
          or Thursday at 09:00 with Luc Martin" turns the call into a decision.
        - It is a search over the plan that was just stored, not a second solve.
          Each eligible assistant's day is a sorted list of visits. The gaps
          between them, and the ends of the day, are where the work could go. A
          gap counts only if it holds the whole service **and** the travel at
          both ends, so a slot offered here is one the next planning run can
          actually take.
        - **Nothing is reserved.** Two operators acting on the same suggestion
          are both told it fits, and the next run settles it. Holding a
          provisional booking would need an expiry, a release path and a screen
          showing what is held — a reservation system, to answer something a
          telephone call resolves.
        - The lunch break is treated as an occupied hour in the middle of the
          window rather than modelled properly. That is deliberately
          conservative: it can only cause a usable slot to be withheld, never an
          unusable one to be offered, and an offer that turns out not to fit is
          the failure that matters.
    """

    def __init__(
        self,
        settings: PlanningSettings,
        travel_minutes: int = 0,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the finder.

        Args:
            settings (PlanningSettings): The working day and break rules.
            travel_minutes (int): Minutes to leave free either side of a slot
                for the drive. A flat allowance rather than a real estimate,
                because the assistant a slot is offered with is not yet fixed.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.settings = settings
        self.travel_minutes = travel_minutes
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("SlotFinder created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _busy_periods(
        self,
        assistant_id: str,
        day: date,
        assignments: List[ScheduledAssignment],
        placed: Dict[str, InterventionRequirement],
    ) -> List[Tuple[int, int]]:
        """Return what already occupies one assistant's day, in order.

        Args:
            assistant_id (str): Whose day it is.
            day (date): The day in question.
            assignments (List[ScheduledAssignment]): The stored plan.
            placed (Dict[str, InterventionRequirement]): The work, by id, so
                each assignment can be matched to its day.

        Returns:
            List[Tuple[int, int]]: Occupied ``(start, end)`` pairs, sorted.

        Notes:
            The lunch break is included as an occupied period. It is not tied
            to a particular hour in the model — the solver places it — so the
            whole configured window is treated as taken. Withholding a slot
            that might have worked is the safe direction.
        """
        busy = [
            (item.start_minute, item.end_minute)
            for item in assignments
            if item.hca_id == assistant_id
            and item.requirement_id in placed
            and placed[item.requirement_id].day == day
        ]
        busy.append(
            (
                self.settings.lunch_window_start_minute,
                self.settings.lunch_window_end_minute,
            )
        )
        return sorted(busy)

    def _gaps(self, busy: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """Return the free stretches of a working day.

        Args:
            busy (List[Tuple[int, int]]): Occupied periods, sorted.

        Returns:
            List[Tuple[int, int]]: The free ``(start, end)`` stretches.

        Notes:
            Overlapping periods are merged as it walks, so two visits that
            touch do not produce a phantom gap of zero length between them.
        """
        gaps: List[Tuple[int, int]] = []
        cursor = self.settings.day_start_minute
        for start, end in busy:
            if start > cursor:
                gaps.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < self.settings.day_end_minute:
            gaps.append((cursor, self.settings.day_end_minute))
        return gaps

    ############################
    # Publicly Exposed Methods #
    ############################

    def find(
        self,
        requirement: InterventionRequirement,
        assistants: List[Hca],
        assignments: List[ScheduledAssignment],
        placed: Dict[str, InterventionRequirement],
        days: List[date],
        limit: int = 3,
    ) -> List[SuggestedSlot]:
        """Return times this work could go instead, best days first.

        Args:
            requirement (InterventionRequirement): The work that did not fit.
            assistants (List[Hca]): The workforce to search over. Already
                filtered to those qualified for this work.
            assignments (List[ScheduledAssignment]): The plan that was stored.
            placed (Dict[str, InterventionRequirement]): The planned work by
                id, so an assignment can be dated.
            days (List[date]): The days to consider, in order.
            limit (int): How many suggestions to return.

        Returns:
            List[SuggestedSlot]: Up to ``limit`` offers, or an empty list when
            the week has no room — which is itself worth reporting.

        Notes:
            - Capped rather than exhaustive. Twenty options is not a choice, it
              is a second problem. Three is enough to telephone a customer with.
            - Days are walked in the order given, so the earliest alternatives
              come first. An operator renegotiating a missed visit is almost
              always trying to move it as little as possible.
        """
        needed = requirement.duration_minutes + 2 * self.travel_minutes
        found: List[SuggestedSlot] = []
        for day in days:
            for assistant in assistants:
                if not assistant.is_schedulable_on(day):
                    continue
                if not assistant.holds_certifications(
                    requirement.required_certification_codes, day
                ):
                    continue
                if not assistant.holds_skills(requirement.required_skill_codes, day):
                    continue
                busy = self._busy_periods(assistant.id or "", day, assignments, placed)
                for start, end in self._gaps(busy):
                    if end - start < needed:
                        continue
                    begin = start + self.travel_minutes
                    found.append(
                        SuggestedSlot(
                            day=day,
                            start_minute=begin,
                            end_minute=begin + requirement.duration_minutes,
                            hca_id=assistant.id or "",
                            hca_name=assistant.full_name(),
                        )
                    )
                    break
                if len(found) >= limit:
                    self.logger.debug(
                        "Found %d slot(s) for %s; stopping the search.",
                        len(found),
                        requirement.id,
                    )
                    return found[:limit]
        if not found:
            self.logger.warning(
                "No free slot anywhere in the period for %s (%s): the week is "
                "full for everybody qualified to do it.",
                requirement.id,
                requirement.name,
            )
        else:
            self.logger.info(
                "Offering %d alternative slot(s) for %s.", len(found), requirement.id
            )
        return found[:limit]
