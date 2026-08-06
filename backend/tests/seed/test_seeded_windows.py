from __future__ import annotations

# Standard library imports
from datetime import time

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from seed.dataset import Dataset


def _minutes(moment: time) -> int:
    """Return a time as minutes from midnight.

    Args:
        moment (time): The time of day.

    Returns:
        int: Minutes since midnight.
    """
    return moment.hour * 60 + moment.minute


class TestTheSeededWindowsFitTheWorkingDay:
    """Tests that the seeded quotes can actually be planned.

    Notes:
        **This is the guard on a fixture that could not be satisfied.** The
        first seeded service window opened at 08:00 while the configured
        working day starts at 09:00, so sixteen of seventy-seven seeded visits
        were outside it. The solver refuses a run it cannot fully satisfy, so
        the whole planning failed — and a freshly seeded stack had no planning
        at all, with nothing on any screen to say why.

        Asserted against the **configuration's** bounds rather than against
        09:00 and 20:00 written again here. Two copies of a number drift, and
        the failure that drift causes is this one.
    """

    @pytest.fixture
    def working_day(self) -> PlanningConfig:
        """Return the planning settings the seeded stack runs with.

        Returns:
            PlanningConfig: The defaults, which the dev configuration keeps.
        """
        return PlanningConfig()

    @pytest.mark.parametrize(
        "window",
        list(Dataset.SERVICE_WINDOWS),
        ids=lambda window: f"{window[0]}-{window[1]}",
    )
    def test_a_window_opens_no_earlier_than_the_day(
        self, window: tuple, working_day: PlanningConfig
    ) -> None:
        """A visit that may start before the day starts can never be placed.

        Args:
            window (tuple): The earliest start, latest end and duration.
            working_day (PlanningConfig): The configured day.
        """
        earliest, _, _ = window

        assert _minutes(earliest) >= working_day.day_start_minute

    @pytest.mark.parametrize(
        "window",
        list(Dataset.SERVICE_WINDOWS),
        ids=lambda window: f"{window[0]}-{window[1]}",
    )
    def test_a_window_closes_no_later_than_the_day(
        self, window: tuple, working_day: PlanningConfig
    ) -> None:
        """Nor one that may run past the end of it.

        Args:
            window (tuple): The earliest start, latest end and duration.
            working_day (PlanningConfig): The configured day.
        """
        _, latest, _ = window

        assert _minutes(latest) <= working_day.day_end_minute

    @pytest.mark.parametrize(
        "window",
        list(Dataset.SERVICE_WINDOWS),
        ids=lambda window: f"{window[0]}-{window[1]}",
    )
    def test_a_visit_fits_inside_its_own_window(self, window: tuple) -> None:
        """A ninety-minute visit in a sixty-minute window is unplaceable.

        Args:
            window (tuple): The earliest start, latest end and duration.
        """
        earliest, latest, duration = window

        assert duration <= _minutes(latest) - _minutes(earliest)
