"""One computation of the planning, and what it produced.

The run is the record an administrator polls; the solution is what the
solver returned; an unplaced requirement is the explanation attached to
work that could not be fitted in.
"""

from .planning_run import PlanningRun
from .planning_solution import PlanningSolution
from .unplaced_requirement import UnplacedRequirement

__all__ = [
    "PlanningRun",
    "PlanningSolution",
    "UnplacedRequirement",
]
