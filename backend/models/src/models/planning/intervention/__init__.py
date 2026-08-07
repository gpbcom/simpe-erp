"""A scheduled visit, and the piece of work it was scheduled from.

The requirement is what the solver is handed; the intervention is what
it decided. They live together because the second is only ever produced
from the first, and neither is read without the other nearby.
"""

from .intervention import Intervention
from .intervention_requirement import InterventionRequirement

__all__ = [
    "Intervention",
    "InterventionRequirement",
]
