"""One computation of the planning, and what it produced.

The run is the record an administrator polls. The solution is what the
solver returned. An unplaced requirement is the explanation attached to
work that could not be fitted in, grouped by the quote it was sold on.
"""

from .planning_run import PlanningRun
from .planning_solution import PlanningSolution
from .suggested_slot import SuggestedSlot
from .unplaced_quote import UnplacedQuote
from .unplaced_requirement import UnplacedRequirement

__all__ = [
    "PlanningRun",
    "PlanningSolution",
    "SuggestedSlot",
    "UnplacedQuote",
    "UnplacedRequirement",
]
