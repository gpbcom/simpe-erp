from __future__ import annotations

# Standard library imports
from pathlib import Path
from typing import List, Tuple

# Third-party imports
from sqlalchemy import Engine, text

# First-party imports
from migration_templates import MigrationTemplates

# First-party imports
from models.enums import Weekday
from models.people.hca import Hca
from models.settings.planning_settings import PlanningSettings

BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: Every table here declares NOT NULL timestamps with no server default, so a
#: raw insert has to supply them. The value is arbitrary; only its presence
#: matters to this test.
STAMP = "'2026-01-01 00:00:00', '2026-01-01 00:00:00'"


class TestMigration0013Backfill:
    """Tests that making the day configurable changes nobody's rota.

    Notes:
        **The schema tests do not cover this.** They compare the migrated
        schema against the ORM metadata, which proves the five columns exist
        and are ``NOT NULL`` — and would pass just as happily if
        ``working_weekdays`` were backfilled with Monday-to-Friday, or if the
        working day were backfilled with zeroes.

        Both would be silent. A five-day backfill cancels every Saturday and
        Sunday round the agency already had, and the only symptom is a planning
        run that suddenly cannot place a weekend visit. A zeroed working day
        would let the solver schedule at midnight.

        So this asserts the two backfills against real rows, and asserts that
        they *disagree*: existing assistants keep the seven-day week they
        effectively had, while the model's default for a new hire stays
        Monday-to-Friday.
    """

    ############################
    # Internal Helpers Methods #
    ############################

    def _seed_an_assistant(self, engine: Engine, hca_id: str = "hca-1") -> None:
        """Insert one company and one assistant as revision 0012 leaves them.

        Args:
            engine (Engine): The database to write to.
            hca_id (str): The assistant's identifier.

        Notes:
            Raw SQL rather than the ORM. The ORM row already declares
            ``working_weekdays``, so inserting through it would supply the very
            column this test checks the migration adds — and the test would
            pass without the backfill ever running.
        """
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO companies (id, name, "
                    "registration_number, is_accepting_applications, "
                    "created_at, updated_at) VALUES ('co1', 'Agency', 'RCS1', "
                    f"1, {STAMP})"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO hcas (id, first_name, last_name, "
                    "phone_number, email, street, postal_code, city, country, "
                    "company_id, contract_type, field_employee, created_at, "
                    f"updated_at) VALUES ('{hca_id}', 'Luc', 'Martin', "
                    f"'+33612345678', '{hca_id}@example.fr', '1 rue', "
                    f"'75001', 'Paris', 'France', 'co1', 'cdi', 1, {STAMP})"
                )
            )

    def _seed_the_settings(self, engine: Engine) -> None:
        """Insert the single planning-settings row as 0012 leaves it.

        Args:
            engine (Engine): The database to write to.
        """
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO planning_settings (id, "
                    "max_intervention_radius_km, lunch_break_minutes, "
                    "created_at, updated_at) VALUES ('planning-settings', "
                    f"30.0, 60, {STAMP})"
                )
            )

    def _working_weeks(self, engine: Engine) -> List[Tuple[str, str]]:
        """Return every assistant's identifier and stored working week.

        Args:
            engine (Engine): The database to read.

        Returns:
            List[Tuple[str, str]]: One pair per assistant.
        """
        with engine.connect() as connection:
            return [
                (row[0], row[1])
                for row in connection.execute(
                    text("SELECT id, working_weekdays FROM hcas ORDER BY id")
                )
            ]

    def _working_day(self, engine: Engine) -> Tuple[int, int, int, int]:
        """Return the stored working day and lunch window.

        Args:
            engine (Engine): The database to read.

        Returns:
            Tuple[int, int, int, int]: Day start, day end, lunch window start
            and lunch window end, in minutes from midnight.
        """
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT day_start_minute, day_end_minute, "
                    "lunch_window_start_minute, lunch_window_end_minute "
                    "FROM planning_settings WHERE id = 'planning-settings'"
                )
            ).one()
        return (row[0], row[1], row[2], row[3])

    ############################
    # Publicly Exposed Methods #
    ############################

    def test_an_existing_assistant_keeps_every_day_they_could_work(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """**The promise: no weekend round is cancelled by a deployment.**

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            Before this column existed the planner would schedule an assistant
            on any day it had work for them, weekends included. A backfill of
            Monday-to-Friday would withdraw them from Saturday and Sunday
            without anybody deciding to — and the first sign would be a
            planning run failing to place a weekend visit.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0012")
        self._seed_an_assistant(engine)

        migrations.apply(engine, "0013")

        assert self._working_weeks(engine) == [
            ("hca-1", "monday,tuesday,wednesday,thursday,friday,saturday,sunday")
        ]

    def test_every_existing_assistant_is_backfilled(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """The backfill reaches every row, not just the first.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0012")
        for index in range(3):
            self._seed_an_assistant(engine, hca_id=f"hca-{index}")

        migrations.apply(engine, "0013")

        stored = self._working_weeks(engine)
        assert len(stored) == 3
        assert {week for _, week in stored} == {
            "monday,tuesday,wednesday,thursday,friday,saturday,sunday"
        }

    def test_the_backfilled_week_parses_back_to_seven_days(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """The stored string is what the mapper expects to read.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            A backfill spelling the days differently — capitalised, or
            space-separated — would satisfy the column's ``NOT NULL`` and then
            fail on the first read, which is a long way from the migration that
            caused it.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0012")
        self._seed_an_assistant(engine)

        migrations.apply(engine, "0013")

        stored = self._working_weeks(engine)[0][1]
        assert [Weekday(value) for value in stored.split(",")] == list(Weekday)

    def test_a_new_assistant_still_defaults_to_the_standard_week(self) -> None:
        """The two defaults disagree deliberately, and that is the design.

        Notes:
            The migration is about not changing anybody's existing rota. The
            model is about what a new hire means by full-time. Making them
            agree either cancels weekend rounds on deployment or puts every new
            hire on a seven-day week.
        """
        assert list(Hca.DEFAULT_WORKING_WEEKDAYS) == [
            Weekday.MONDAY,
            Weekday.TUESDAY,
            Weekday.WEDNESDAY,
            Weekday.THURSDAY,
            Weekday.FRIDAY,
        ]

    def test_the_stored_working_day_keeps_the_shipped_hours(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """The agency's day does not move because it became editable.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The existing row was written under 09:00-20:00 with lunch between
            11:30 and 14:30. Backfilling anything else — zeroes, or a different
            default — would change how the agency plans on the deployment that
            was only supposed to make the values reachable.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0012")
        self._seed_the_settings(engine)

        migrations.apply(engine, "0013")

        assert self._working_day(engine) == (
            9 * 60,
            20 * 60,
            11 * 60 + 30,
            14 * 60 + 30,
        )

    def test_the_backfilled_working_day_satisfies_the_model(
        self, tmp_path: Path, migrations: MigrationTemplates
    ) -> None:
        """What the migration wrote is a settings row the model accepts.

        Args:
            tmp_path (Path): Scratch directory.
            migrations (MigrationTemplates): The shared template cache.

        Notes:
            The lunch window has to sit inside the working day and be wide
            enough to hold the break. A backfill that got that wrong would pass
            every schema check and then raise on the first read of the row.
        """
        engine = migrations.copy_to(tmp_path / "before.db", stop_after="0012")
        self._seed_the_settings(engine)

        migrations.apply(engine, "0013")
        day_start, day_end, lunch_start, lunch_end = self._working_day(engine)

        rebuilt = PlanningSettings(
            max_intervention_radius_km=30.0,
            day_start_minute=day_start,
            day_end_minute=day_end,
            lunch_break_minutes=60,
            lunch_window_start_minute=lunch_start,
            lunch_window_end_minute=lunch_end,
        )

        assert rebuilt.describe_working_day() == "09:00–20:00"
