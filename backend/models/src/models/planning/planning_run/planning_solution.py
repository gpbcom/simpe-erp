from __future__ import annotations

# Standard library imports
from typing import Dict, List, Optional

# Third-party imports
from pydantic import BaseModel, ConfigDict, Field


class ScheduledAssignment(BaseModel):
    """One requirement, placed with an assistant at an exact time.

    Attributes:
        requirement_id (str): The requirement that was placed.
        hca_id (str): The assistant it was given to.
        start_minute (int): When it starts, in minutes from midnight.
        end_minute (int): When it ends, in minutes from midnight.

    Notes:
        The solver's raw output, before it becomes an
        :class:`~models.planning.intervention.Intervention`. It carries only
        what the solver decided — who and when — so the model that turns it
        into a visit is the one place names and addresses get attached.
    """

    model_config = ConfigDict(frozen=True)

    requirement_id: str = Field(description="The requirement that was placed.")
    hca_id: str = Field(description="The assistant it was given to.")
    start_minute: int = Field(description="When it starts, from midnight.")
    end_minute: int = Field(description="When it ends, from midnight.")


class PlanningSolution(BaseModel):
    """What one run of the solver produced.

    Attributes:
        assignments (List[ScheduledAssignment]): The work that was placed.
        unassigned_requirement_ids (List[str]): The work that was not.
        total_travel_minutes (int): Travel time across every assistant's round.
        is_feasible (bool): Whether the solver found any solution at all.
        status_name (str): The solver's own status, for the log.

    Notes:
        A solution with unplaced work is still a solution. The solver may leave
        a requirement out — at a large objective penalty — rather than fail
        outright, because a plan covering most of the week plus an explicit
        list of what did not fit is far more useful to a manager than no plan
        and no explanation.

        ``is_feasible`` false is different: the solver found nothing, which
        means the constraints contradict each other rather than the workload
        being too big.

        ``is_optimised`` is a third, weaker thing again, and it is about the
        *rounds* rather than about the work. A plan is found in two passes:
        the first places everything, the second shortens the driving. If the
        second runs out of budget the first pass's plan is kept and this stays
        false — every visit is still scheduled, the travel simply was not
        proved minimal. It is recorded because a plan nobody can tell apart
        from an optimised one is how a slow creep in travel goes unnoticed.
    """

    assignments: List[ScheduledAssignment] = Field(
        default_factory=list,
        description="The work that was placed.",
    )
    unassigned_requirement_ids: List[str] = Field(
        default_factory=list,
        description="The work that was not placed.",
    )
    total_travel_minutes: int = Field(
        default=0,
        description="Travel time across every assistant's round.",
    )
    is_feasible: bool = Field(
        default=False,
        description="Whether the solver found any solution.",
    )
    is_optimised: bool = Field(
        default=False,
        description="Whether the travel in this plan was proved minimal.",
    )
    status_name: str = Field(
        default="UNKNOWN",
        description="The solver's own status, for the log.",
    )

    def assignments_by_hca(self) -> Dict[str, List[ScheduledAssignment]]:
        """Return the placed work grouped by assistant, in time order.

        Returns:
            Dict[str, List[ScheduledAssignment]]: Each assistant's round.
        """
        grouped: Dict[str, List[ScheduledAssignment]] = {}
        for assignment in self.assignments:
            grouped.setdefault(assignment.hca_id, []).append(assignment)
        for round_ in grouped.values():
            round_.sort(key=lambda entry: entry.start_minute)
        return grouped

    def assignment(self, requirement_id: str) -> Optional[ScheduledAssignment]:
        """Return where a requirement was placed, if it was.

        Args:
            requirement_id (str): The requirement to look up.

        Returns:
            Optional[ScheduledAssignment]: Its placement, or ``None`` when it
            was left unassigned.
        """
        for assignment in self.assignments:
            if assignment.requirement_id == requirement_id:
                return assignment
        return None

    def is_complete(self) -> bool:
        """Return whether every requirement was placed.

        Returns:
            bool: ``True`` when the solve was feasible and nothing was left
            over.
        """
        return self.is_feasible and not self.unassigned_requirement_ids
