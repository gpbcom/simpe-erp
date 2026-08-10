from __future__ import annotations

# Standard library imports
from typing import List, Optional

# First-party imports
from models.enums import UnplacedReason
from models.people.hca import Hca
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.settings.planning_settings import PlanningSettings


class PlanningScenario:
    """One named planning instance, with what it is expected to produce.

    Attributes:
        name (str): What the case is, used as the parametrised test id.
        requirements (List[InterventionRequirement]): The work.
        assistants (List[Hca]): The workforce.
        settings (PlanningSettings): The manager-owned rules.
        expect_feasible (bool): Whether the solver should find any plan.
        expect_unplaced_ids (List[str]): Which work should not be placed.
        expect_reason (Optional[UnplacedReason]): The reason the diagnosis
            should give for the first unplaced item, or ``None`` not to assert
            on it.
        expect_assignee (Optional[str]): Which assistant should get the first
            requirement, when the case is about *who* rather than *whether*.
        radius_km (Optional[float]): Recorded only so a failure message can
            say what the instance was.

    Notes:
        - A plain class rather than a Pydantic model on purpose. The house rule
          is that Pydantic models live in ``models/`` and carry validators,
          exceptions and their own tests — and this is a test fixture, not a
          domain concept. Putting it in the domain would mean the shipped
          application gained a class that exists only for the test suite.
        - The expectation lives beside the instance rather than in the test that
          runs it, so a case is one readable block and the harness stays a
          single parametrised function.
    """

    def __init__(
        self,
        name: str,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
        settings: PlanningSettings,
        expect_feasible: bool = True,
        expect_unplaced_ids: Optional[List[str]] = None,
        expect_reason: Optional[UnplacedReason] = None,
        expect_assignee: Optional[str] = None,
    ) -> None:
        """Initialize the scenario.

        Args:
            name (str): What the case is.
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.
            settings (PlanningSettings): The rules in force.
            expect_feasible (bool): Whether any plan should be found.
            expect_unplaced_ids (Optional[List[str]]): Work expected to go
                unplaced. Defaults to none.
            expect_reason (Optional[UnplacedReason]): Expected diagnosis.
            expect_assignee (Optional[str]): Expected holder of the first
                requirement.
        """
        self.name = name
        self.requirements = requirements
        self.assistants = assistants
        self.settings = settings
        self.expect_feasible = expect_feasible
        self.expect_unplaced_ids = expect_unplaced_ids or []
        self.expect_reason = expect_reason
        self.expect_assignee = expect_assignee

    def __repr__(self) -> str:
        """Return the scenario's name.

        Returns:
            str: The name, so pytest ids read as sentences.
        """
        return self.name
