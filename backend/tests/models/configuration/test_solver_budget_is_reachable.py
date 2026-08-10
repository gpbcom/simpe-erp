from __future__ import annotations

# Standard library imports
from pathlib import Path

# Third-party imports
import pytest

# First-party imports
from models.configuration.app_config import AppConfig

BACKEND_ROOT = Path(__file__).resolve().parents[3]
SHIPPED_CONFIGS = ("app.yaml", "app.dev.yaml", "app.docker.yaml")

# The wall-clock net has to be far enough above each budget that the budget is
# what actually stops the search.
#
# **Twenty, matching the same floor in infra/chart/templates/common/guards.yaml.**
# It read eight here, drawn from a one-worker measurement while every shipped
# config ran eight workers — so it passed the very pairing it exists to catch: a
# net of 900 against a budget of 100, which truncated every search and left a
# 95-visit week one visit short at status FEASIBLE. Two copies of a floor that
# disagree are worse than one, because whichever is looser is the one that
# decides.
MINIMUM_NET_TO_BUDGET_RATIO = 20.0


class TestTheSolverBudgetIsReachable:
    """Tests that the search is stopped by its budget, not by its safety net.

    Notes:
        **These two settings measure different things** — ``solver_time_limit``
        is seconds and ``solver_deterministic_budget`` is solver work units —
        so nothing makes them agree by construction, and a pair that disagrees
        is silent. The search stops early, the plan comes back with visits
        unplaced that a full search places, and the only trace is one WARNING
        saying the run was not reproducible.

        The Helm chart shipped exactly that: it pinned the net at 30.0 and
        never set the budget at all, so every solve in a cluster stopped a
        fifth of the way into the search it needed. ``infra/chart`` now refuses
        to render that, and this is the same check on the side of the system
        that actually reads these files.
    """

    @pytest.mark.parametrize("name", SHIPPED_CONFIGS)
    def test_the_net_is_far_above_the_budget(self, name: str) -> None:
        """A net below the budget's real cost truncates every solve.

        Args:
            name (str): The shipped configuration file under test.
        """
        planning = AppConfig.load(BACKEND_ROOT / "conf" / name).planning

        # Both passes are bounded by the same net, so it has to clear the
        # larger of them. Checking only the feasibility budget would let an
        # optimisation budget be configured that can never be spent — and its
        # symptom is the quietest one there is: every visit still placed, the
        # rounds just longer than they need to be.
        largest = max(
            planning.solver_deterministic_budget,
            planning.solver_optimisation_budget,
        )
        assert planning.solver_time_limit_seconds >= (
            largest * MINIMUM_NET_TO_BUDGET_RATIO
        ), (
            f"conf/{name}: a wall-clock net of "
            f"{planning.solver_time_limit_seconds}s cannot let a per-day "
            f"budget of {largest} finish."
        )

    def test_every_shipped_config_agrees_on_the_solver(self) -> None:
        """One environment planning differently from another is a bug, not a setting.

        Notes:
            Deployment overlays legitimately differ on hosts, credentials and
            replica counts. The solver settings are not that kind of knob: they
            decide *what plan comes out*, so a week that plans one way on a
            developer's machine and another in production cannot be reasoned
            about at all. They are pinned together here rather than left to
            three files drifting apart.
        """
        # Every setting that decides what plan comes out, not just the two
        # that did when the solve was one model and one pass. A day
        # concurrency or an optimisation budget that differed between
        # environments would be exactly the same class of bug: the same week
        # planning differently in two places, with nothing on either screen to
        # say why.
        settings = [
            (
                AppConfig.load(BACKEND_ROOT / "conf" / name).planning.model_dump(
                    include={
                        "solver_deterministic_budget",
                        "solver_optimisation_budget",
                        "solver_time_limit_seconds",
                        "solver_seed",
                        "solver_workers",
                        "solver_day_concurrency",
                    }
                )
            )
            for name in SHIPPED_CONFIGS
        ]

        for key in settings[0]:
            values = [entry[key] for entry in settings]
            assert len(set(values)) == 1, f"{key} differs across configs: {values}"

    @pytest.mark.parametrize("name", SHIPPED_CONFIGS)
    def test_dropping_work_outranks_any_possible_travel(self, name: str) -> None:
        """The penalty has to dominate travel, or the solver drops distant visits.

        Args:
            name (str): The shipped configuration file under test.

        Notes:
            The objective trades one unplaced visit against the travel needed
            to reach it. If a full week's travel could ever cost more than one
            penalty, the cheapest plan is to abandon the furthest customer —
            technically optimal and commercially indefensible. A measured week
            of 77 visits travels about 500 minutes in total, so the penalty
            needs to stand well clear of that.
        """
        planning = AppConfig.load(BACKEND_ROOT / "conf" / name).planning

        assert planning.unassigned_penalty > planning.travel_weight * 10_000, (
            f"conf/{name}: an unassigned penalty of "
            f"{planning.unassigned_penalty} does not clearly outrank a week of "
            f"travel weighted at {planning.travel_weight}."
        )
