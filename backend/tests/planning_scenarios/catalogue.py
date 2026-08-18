from __future__ import annotations

# Standard library imports
from datetime import date, time
from typing import List

# First-party imports
from models.enums import UnplacedReason, Weekday
from models.geo.geo_point import GeoPoint
from models.people.hca.certification import Certification
from models.people.hca.skill import Skill

# Local imports
from tests.planning_scenarios.builder import ScenarioBuilder
from tests.planning_scenarios.scenario import PlanningScenario


class ScenarioCatalogue:
    """Every planning case worth pinning, as runnable instances.

    Attributes:
        build (ScenarioBuilder): Builds the assistants, requirements and
            settings every case is assembled from, so two cases that mean the
            same thing are spelled the same way.
        monday (date): The first day of the fixture week, taken from the
            builder so the whole catalogue agrees on when "Monday" is.
        tuesday (date): The second day, for the cases that need work to span
            more than one.
        wednesday (date): The third, for the decomposition cases.

    Notes:
        - **This is the regression net for the per-day refactor.** Each case is
          a fact about the solver that must survive a change to how the model is
          built, so the harness that runs them must pass unmodified before and
          after. A case that has to be edited to go green is a behaviour change
          that needs justifying, not a test that needs fixing.
        - Two things are deliberately *not* here:

          1) **A window narrower than its duration.** That is refused by
             :meth:`InterventionRequirement.check_window` before the solver ever
             sees it, and belongs with the model tests.
          2) **``field_employee`` false.** Office staff are filtered out by
             ``PlanningService._field_employees`` upstream of ``solve``, so a
             scenario here would prove nothing about the filter.
             ``tests/service/test_planning_field_employees.py`` covers it.

        - Where the expected diagnosis is not obvious from the constraint alone,
          ``expect_reason`` is left ``None`` and only the unplaced set is
          asserted. Guessing a reason and then discovering the solver disagrees
          would encode the guess rather than the behaviour.
    """

    def __init__(self) -> None:
        """Initialize the catalogue over a shared builder.

        Notes:
            One builder for every case, rather than one each. The builder's
            defaults are what make two scenarios comparable — a case that
            quietly built its own assistant would differ from its neighbours in
            ways no reader could see.
        """
        self.build = ScenarioBuilder()
        self.monday = ScenarioBuilder.MONDAY
        self.tuesday = date(2026, 8, 4)
        self.wednesday = date(2026, 8, 5)

    ##########################################
    # Group 1 — Every unplaced reason        #
    ##########################################

    def missing_certification(self) -> PlanningScenario:
        """Work nobody is qualified for is left out, not given to anybody.

        Returns:
            PlanningScenario: One visit requiring DEAES and one assistant who does
                not hold it.
        """
        return PlanningScenario(
            name="missing-certification",
            requirements=[self.build.requirement(certification_codes=["DEAES"])],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.MISSING_CERTIFICATION,
        )

    def missing_skill(self) -> PlanningScenario:
        """A declared skill is as hard a constraint as a diploma.

        Returns:
            PlanningScenario: One visit requiring a declared skill and one
                assistant who has not declared it.
        """
        return PlanningScenario(
            name="missing-skill",
            requirements=[self.build.requirement(skill_codes=["LEVE-PERSONNE"])],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.MISSING_SKILL,
        )

    def missing_both(self) -> PlanningScenario:
        """Blocked by both, the certification is reported.

        Returns:
            PlanningScenario: One visit short of both a certification and a skill,
                and one assistant with neither.

        Notes:
            The two are fixed by different people — a certification is a hire
            or a course, a skill may be somebody who can already do the work
            not having said so — so the ladder puts the harder problem first.
        """
        return PlanningScenario(
            name="missing-both-reports-the-certification",
            requirements=[
                self.build.requirement(
                    certification_codes=["DEAES"], skill_codes=["LEVE-PERSONNE"]
                )
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.MISSING_CERTIFICATION,
        )

    def qualified_assistant_is_chosen(self) -> PlanningScenario:
        """The gate selects rather than merely excluding.

        Returns:
            PlanningScenario: One visit needing a skill and two
                assistants, only the second of whom has it.
        """
        return PlanningScenario(
            name="the-qualified-assistant-is-chosen",
            requirements=[self.build.requirement(skill_codes=["CUISINE"])],
            assistants=[
                self.build.assistant("hca-1"),
                self.build.assistant(
                    "hca-2", skills=[Skill(name="Cuisine", code="CUISINE")]
                ),
            ],
            settings=self.build.settings(),
            expect_assignee="hca-2",
        )

    def not_a_working_day(self) -> PlanningScenario:
        """Nobody works Mondays, so Monday's work does not happen.

        Returns:
            PlanningScenario: Monday work, and an assistant who works only
                Tuesdays.
        """
        return PlanningScenario(
            name="not-a-working-day",
            requirements=[self.build.requirement(day=self.monday)],
            assistants=[self.build.assistant(working_weekdays=[Weekday.TUESDAY])],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.NOT_A_WORKING_DAY,
        )

    def whole_day_absence(self) -> PlanningScenario:
        """A dated absence is different from never working that weekday.

        Returns:
            PlanningScenario: Monday work, and an assistant absent that whole
                day.
        """
        return PlanningScenario(
            name="whole-day-absence",
            requirements=[self.build.requirement(day=self.monday)],
            assistants=[
                self.build.assistant(
                    availability=[self.build.absence("hca-1", self.monday)]
                )
            ],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.NO_ASSISTANT_AVAILABLE,
        )

    def out_of_radius(self) -> PlanningScenario:
        """Beyond the radius is a hard exclusion, not an expensive drive.

        Returns:
            PlanningScenario: A visit beyond the configured radius, and one
                assistant inside it.
        """
        return PlanningScenario(
            name="out-of-radius",
            requirements=[self.build.requirement(location=ScenarioBuilder.FAR_AWAY)],
            assistants=[self.build.assistant()],
            settings=self.build.settings(radius_km=30.0),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.OUT_OF_RADIUS,
        )

    def customer_conflict(self) -> PlanningScenario:
        """One customer cannot be in two places at once, whoever drives.

        Returns:
            PlanningScenario: Two ninety-minute visits for one customer inside a
                two-hour window, with two assistants free.

        Notes:
            - Two ninety-minute visits inside one two-hour window need 180
              minutes and have 120. Two assistants are supplied on purpose: the
              constraint being tested is the customer's, not the workforce's.
            - The two visits are symmetric, so *which* one is dropped is a
              tie-break rather than a consequence of the constraint. The id
              below is the one today's solver drops, recorded from a baseline
              run rather than guessed. Keeping it exact is deliberate: if a
              refactor changes it, that is a change in tie-breaking worth
              noticing and explaining, not something a looser assertion should
              hide.
        """
        return PlanningScenario(
            name="customer-conflict",
            requirements=[
                self.build.requirement(
                    "req-1", customer_id="cust-1", duration_minutes=90
                ),
                self.build.requirement(
                    "req-2", customer_id="cust-1", duration_minutes=90
                ),
            ],
            assistants=[
                self.build.assistant("hca-1"),
                self.build.assistant("hca-2"),
            ],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-2"],
        )

    def no_feasible_slot(self) -> PlanningScenario:
        """Travel, not qualification or distance, is what leaves no room.

        Returns:
            PlanningScenario: Two visits fifteen kilometres either side of home in
                one window, and a single assistant to drive between them.

        Notes:
            Two visits fifteen kilometres either side of home, both inside the
            same two-hour window, one assistant. Each is well within the
            radius and needs nothing. The hour of driving between them is what
            makes the second impossible.
        """
        north = GeoPoint(
            latitude=ScenarioBuilder.HOME.latitude + 0.135,
            longitude=ScenarioBuilder.HOME.longitude,
        )
        south = GeoPoint(
            latitude=ScenarioBuilder.HOME.latitude - 0.135,
            longitude=ScenarioBuilder.HOME.longitude,
        )
        return PlanningScenario(
            name="no-feasible-slot",
            requirements=[
                self.build.requirement("req-1", location=north),
                self.build.requirement("req-2", location=south),
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-2"],
        )

    def outside_working_day(self) -> PlanningScenario:
        """A window outside the agency's hours contradicts, it does not drop.

        Returns:
            PlanningScenario: A visit windowed before the agency opens, which
                the solver must prove infeasible rather than leave unplaced.

        Notes:
            ``_add_day_bounds`` applies to every requirement whether or not it
            is assigned, so this is the one ordinary input that makes the
            model INFEASIBLE rather than merely leaving work unplaced. The
            distinction is load-bearing: it earns the "the solver proved it"
            wording that a search which merely ran out of time may not use.
        """
        early = self.build.requirement()
        early = early.model_copy(
            update={
                "window_start_minute": 6 * 60,
                "window_end_minute": 8 * 60,
                "duration_minutes": 60,
            }
        )
        return PlanningScenario(
            name="outside-working-day",
            requirements=[early],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
            expect_feasible=False,
        )

    ##########################################
    # Group 2 — Every solver outcome         #
    ##########################################

    def everything_placed(self) -> PlanningScenario:
        """The ordinary case, and the control for every other.

        Returns:
            PlanningScenario: Two visits in separate windows and one assistant
                who can take both.
        """
        return PlanningScenario(
            name="everything-placed",
            requirements=[
                self.build.requirement("req-1", window=0),
                self.build.requirement("req-2", window=3),
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
        )

    def empty_week(self) -> PlanningScenario:
        """A week with no accepted work is an answer, not an error.

        Returns:
            PlanningScenario: No work at all, and one idle assistant.
        """
        return PlanningScenario(
            name="empty-week",
            requirements=[],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
        )

    def no_assistants(self) -> PlanningScenario:
        """Nobody to plan for leaves everything unplaced, feasibly.

        Returns:
            PlanningScenario: One visit and nobody to send.
        """
        return PlanningScenario(
            name="no-assistants",
            requirements=[self.build.requirement()],
            assistants=[],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
        )

    def unroutable_home(self) -> PlanningScenario:
        """An assistant whose home never geocoded can be sent nowhere.

        Returns:
            PlanningScenario: One visit and an assistant whose home never
                geocoded.

        Notes:
            Travel from an unknown point is not estimable, so the ban is
            total rather than per-requirement — which is why it is worth its
            own case rather than folding into the radius.
        """
        return PlanningScenario(
            name="unroutable-home",
            requirements=[self.build.requirement()],
            assistants=[self.build.homeless_assistant()],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
        )

    ##########################################
    # Group 3 — Decomposition correctness    #
    ##########################################

    def independent_days(self) -> PlanningScenario:
        """Three days of work that share nothing must all be planned.

        Returns:
            PlanningScenario: Three visits on three days that share no
                constraint.
        """
        return PlanningScenario(
            name="independent-days",
            requirements=[
                self.build.requirement("req-1", day=self.monday),
                self.build.requirement("req-2", day=self.tuesday),
                self.build.requirement("req-3", day=self.wednesday),
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
        )

    def same_window_on_two_days(self) -> PlanningScenario:
        """The same hour on two days is two slots, not one.

        Returns:
            PlanningScenario: The same hour booked on Monday and on
                Tuesday.

        Notes:
            ``start`` and ``end`` are minutes from midnight with no day
            offset, which is safe only because every no-overlap set is
            day-scoped. A decomposition that merged two days, or a merge that
            shared a resource across them, shows up here and almost nowhere
            else.
        """
        return PlanningScenario(
            name="same-window-on-two-days",
            requirements=[
                self.build.requirement("req-1", day=self.monday, window=0),
                self.build.requirement("req-2", day=self.tuesday, window=0),
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
        )

    def shared_customer_across_days(self) -> PlanningScenario:
        """One customer, two days: no conflict, because conflict is per day.

        Returns:
            PlanningScenario: One customer visited on two different
                days.
        """
        return PlanningScenario(
            name="shared-customer-across-days",
            requirements=[
                self.build.requirement("req-1", day=self.monday, customer_id="cust-1"),  # noqa: E501
                self.build.requirement("req-2", day=self.tuesday, customer_id="cust-1"),  # noqa: E501
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
        )

    def one_infeasible_day_among_feasible(self) -> PlanningScenario:
        """A period is refused as a whole, however good its other days.

        Returns:
            PlanningScenario: A workable Monday beside a Tuesday
                windowed before the agency opens.

        Notes:
            The all-or-nothing gate is over the period, not the day. A
            calendar missing Tuesday still looks like a calendar, and the
            visits quietly dropped are the ones that end with somebody
            waiting at the door.
        """
        early = self.build.requirement("req-2", day=self.tuesday)
        early = early.model_copy(
            update={
                "window_start_minute": 6 * 60,
                "window_end_minute": 8 * 60,
                "duration_minutes": 60,
            }
        )
        return PlanningScenario(
            name="one-infeasible-day-among-feasible",
            requirements=[
                self.build.requirement("req-1", day=self.monday),
                early,
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
            expect_feasible=False,
        )

    ##########################################
    # Group 4 — Edge cases in the data       #
    ##########################################

    def certification_expired_on_the_visit_day(self) -> PlanningScenario:
        """Expiry is judged on the day of the visit, not on today.

        Returns:
            PlanningScenario: A visit needing SST, and an
                assistant whose SST lapsed the day before it.
        """
        return PlanningScenario(
            name="certification-expired-on-the-visit-day",
            requirements=[
                self.build.requirement(day=self.monday, certification_codes=["SST"])
            ],
            assistants=[
                self.build.assistant(
                    certifications=[
                        Certification(
                            name="Sauveteur",
                            code="SST",
                            expires_on=date(2026, 7, 31),
                        )
                    ]
                )
            ],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.MISSING_CERTIFICATION,
        )

    def certification_still_valid_on_the_visit_day(self) -> PlanningScenario:
        """The control for the case above, so it cannot pass vacuously.

        Returns:
            PlanningScenario: The same pair, with the
                certification still in date.
        """
        return PlanningScenario(
            name="certification-still-valid-on-the-visit-day",
            requirements=[
                self.build.requirement(day=self.monday, certification_codes=["SST"])
            ],
            assistants=[
                self.build.assistant(
                    certifications=[
                        Certification(
                            name="Sauveteur",
                            code="SST",
                            expires_on=date(2026, 12, 31),
                        )
                    ]
                )
            ],
            settings=self.build.settings(),
        )

    def skill_expired_on_the_visit_day(self) -> PlanningScenario:
        """A declared skill expires the same way a diploma does.

        Returns:
            PlanningScenario: A visit needing a language, and an
                assistant whose declaration of it has lapsed.
        """
        return PlanningScenario(
            name="skill-expired-on-the-visit-day",
            requirements=[
                self.build.requirement(day=self.monday, skill_codes=["ARABE"])
            ],
            assistants=[
                self.build.assistant(
                    skills=[
                        Skill(name="Arabe", code="ARABE", expires_on=date(2026, 7, 31))
                    ]
                )
            ],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
            expect_reason=UnplacedReason.MISSING_SKILL,
        )

    def partial_day_absence_blocks_only_its_hours(self) -> PlanningScenario:
        """A morning off leaves the afternoon usable.

        Returns:
            PlanningScenario: A morning and an afternoon
                visit, against an assistant absent only in the morning.

        Notes:
            The whole-day and partial-day absences are one model but two
            different constraints — one bans the day, the other becomes a
            fixed interval inside the assistant's own no-overlap. Asserting
            that the afternoon visit still lands is what tells the two apart.
        """
        return PlanningScenario(
            name="partial-day-absence-blocks-only-its-hours",
            requirements=[
                self.build.requirement("req-1", day=self.monday, window=0),
                self.build.requirement("req-2", day=self.monday, window=3),
            ],
            assistants=[
                self.build.assistant(
                    availability=[
                        self.build.absence(
                            "hca-1",
                            self.monday,
                            start_time=time(9, 0),
                            end_time=time(12, 0),
                        )
                    ]
                )
            ],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-1"],
        )

    def lunch_cannot_be_squeezed_out(self) -> PlanningScenario:
        """The break is a constraint, not a preference the solver may drop.

        Returns:
            PlanningScenario: Three one-hour visits sharing a window
                that must also accommodate an hour of lunch.

        Notes:
            - Three one-hour visits sharing an 11:30-14:00 window, one
              assistant, and an hour of lunch that must also land between 11:30
              and 14:30. Only one visit fits, and the plan comes back two
              short rather than silently working somebody through their break.
            - Which two are dropped is a tie-break between symmetric visits;
              the ids below are what today's solver returns, recorded from a
              baseline run. Kept exact on purpose — a refactor that changes
              them is changing tie-breaking, which is worth explaining rather
              than hiding behind a looser assertion.
        """
        return PlanningScenario(
            name="lunch-cannot-be-squeezed-out",
            requirements=[
                self.build.requirement("req-1", window=2),
                self.build.requirement("req-2", window=2),
                self.build.requirement("req-3", window=2),
            ],
            assistants=[self.build.assistant()],
            settings=self.build.settings(),
            expect_unplaced_ids=["req-2", "req-3"],
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def all(self) -> List[PlanningScenario]:
        """Return every scenario, in a stable order.

        Returns:
            List[PlanningScenario]: The whole catalogue.

        Notes:
            Listed explicitly rather than discovered by introspection. A
            catalogue that finds its own members hides the one that was
            deleted, and the point of this file is that nothing goes missing
            quietly.
        """
        return [
            # Group 1 — every unplaced reason
            self.missing_certification(),
            self.missing_skill(),
            self.missing_both(),
            self.qualified_assistant_is_chosen(),
            self.not_a_working_day(),
            self.whole_day_absence(),
            self.out_of_radius(),
            self.customer_conflict(),
            self.no_feasible_slot(),
            self.outside_working_day(),
            # Group 2 — every solver outcome
            self.everything_placed(),
            self.empty_week(),
            self.no_assistants(),
            self.unroutable_home(),
            # Group 3 — decomposition correctness
            self.independent_days(),
            self.same_window_on_two_days(),
            self.shared_customer_across_days(),
            self.one_infeasible_day_among_feasible(),
            # Group 4 — edge cases in the data
            self.certification_expired_on_the_visit_day(),
            self.certification_still_valid_on_the_visit_day(),
            self.skill_expired_on_the_visit_day(),
            self.partial_day_absence_blocks_only_its_hours(),
            self.lunch_cannot_be_squeezed_out(),
        ]
