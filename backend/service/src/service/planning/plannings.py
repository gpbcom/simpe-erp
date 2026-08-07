from __future__ import annotations

# Standard library imports
import asyncio
from time import monotonic
from collections import defaultdict
from datetime import UTC, date, datetime, time
from logging import Logger, getLogger
import math
from typing import Dict, List, Optional, Tuple

# Third-party imports
from ortools.sat.python import cp_model

# First-party imports
from models.auth.user import User
from models.catalog.intervention_type import InterventionType
from models.configuration.planning_config import PlanningConfig
from models.enums import EventRoutingKey, PlanningRunStatus, UnplacedReason
from models.geo.geo_point import GeoPoint
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.people.hca import Hca
from models.planning.hca_planning import HcaPlanning
from models.planning.intervention import Intervention
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.planning.planning_run import PlanningRun
from models.planning.planning_run.planning_solution import (
    PlanningSolution,
    ScheduledAssignment,
)
from models.planning.planning_run.unplaced_requirement import UnplacedRequirement
from models.quoting.quote import Quote
from models.settings.planning_settings import PlanningSettings
from service.messaging.publisher import EventPublisher
from service.observability.metrics import ApplicationMetrics
from service.planning.exceptions import (
    MTPlanningForbidden,
    MTPlanningInconsistentSolution,
    MTPlanningInfeasible,
    MTPlanningInvalidSpeed,
    MTPlanningRunNotFound,
    MTPlanningSettingsUnavailable,
)
from storage.repositories.catalog.intervention_type import InterventionTypeRepository
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.people.hca import HcaRepository
from storage.repositories.planning.intervention import InterventionRepository
from storage.repositories.planning.planning_run import PlanningRunRepository
from storage.repositories.planning.planning_settings import PlanningSettingsRepository
from storage.repositories.quoting.quote import QuoteRepository


class PlanningService:
    """Owns the planning: its rules, its computation, and the diaries it makes.

    Attributes:
        runs (PlanningRunRepository): The run records.
        interventions (InterventionRepository): The scheduled visits.
        quotes (QuoteRepository): The accepted work.
        customers (CustomerRepository): Where the work happens.
        hcas (HcaRepository): The workforce.
        types (InterventionTypeRepository): The service catalogue, read for the
            qualifications each kind of work requires.
        settings (PlanningSettingsRepository): The store holding the radius and
            lunch-break rules a manager owns.
        config (PlanningConfig): Day bounds, lunch rules, travel speeds.
        travel_points (Dict[str, List[GeoPoint]]): Each assistant's distinct
            places, in index order.
        travel_indexes (Dict[str, Dict[Tuple[float, float], int]]): Each
            assistant's place-to-index lookup.
        travel_minutes (Dict[str, Dict[Tuple[int, int], int]]): Each
            assistant's travel time between every ordered pair.
        logger (Logger): Logger for planning operations.

    Notes:
        - One service for the whole planning entity. The manager-owned rules,
          the solve, and the diagnosis of what would not fit were three classes
          reading the same :class:`~models.configuration.planning_config.PlanningConfig`
          and passing each other the same settings; they answer one question —
          what is the plan, and why is it that — so they answer it from one
          place.
        - The solve is CPU-bound and can run for the configured budget, so it is
          pushed onto a worker thread with :func:`asyncio.to_thread`. Running it
          inline would block the event loop for the whole search, stalling every
          other request in the process.
        - A run's result **replaces** the plan for its period, in one
          transaction. A caller refreshing mid-replan sees the old plan or the
          new one, never a blank week.
        - The rules are read from the store on every solve rather than cached on
          the instance. A service is request-scoped, but a background run
          outlives the request that asked for it, and a radius edited while the
          solver works must not be read from a stale copy.
    """

    def __init__(
        self,
        runs: PlanningRunRepository,
        interventions: InterventionRepository,
        quotes: QuoteRepository,
        customers: CustomerRepository,
        hcas: HcaRepository,
        types: InterventionTypeRepository,
        settings: PlanningSettingsRepository,
        config: PlanningConfig,
        metrics: Optional[ApplicationMetrics] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            runs (PlanningRunRepository): The run records.
            interventions (InterventionRepository): The scheduled visits.
            quotes (QuoteRepository): The accepted work.
            customers (CustomerRepository): Where the work happens.
            hcas (HcaRepository): The workforce.
            types (InterventionTypeRepository): The service catalogue.
            settings (PlanningSettingsRepository): The manager-owned rules.
            config (PlanningConfig): Planning parameters.
            metrics (Optional[ApplicationMetrics]): Where run figures are
                recorded. ``None`` records nothing.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.

        Notes:
            Metrics are optional, and a service given none records nothing
            rather than failing. The API constructs one of these per request to
            answer a read; a registry per request would be six new time series
            a second, all of them thrown away. Only the worker — which is where
            a run is actually executed — passes one in.
        """
        self.runs = runs
        self.interventions = interventions
        self.quotes = quotes
        self.customers = customers
        self.hcas = hcas
        self.types = types
        self.settings = settings
        self.config = config
        self.metrics = metrics
        self.logger = logger if logger else getLogger(__name__)
        self.travel_points: Dict[str, List[GeoPoint]] = {}
        self.travel_indexes: Dict[str, Dict[Tuple[float, float], int]] = {}
        self.travel_minutes: Dict[str, Dict[Tuple[int, int], int]] = {}
        self.logger.debug("PlanningService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _field_employees(self, workforce: List[Hca]) -> List[Hca]:
        """Keep only the people the planner may put on a round.

        Args:
            workforce (List[Hca]): Every assistant record the agency holds.

        Returns:
            List[Hca]: Those marked as field employees.

        Notes:
            - **The single point where who-may-be-scheduled is decided.** Before
              this existed the planner took every assistant record there was, so
              an office-based coordinator with a record — or a manager who holds
              one because they also cover rounds — was equally schedulable and
              equally not. The flag is on the person rather than derived from
              their account's role, because neither answer follows from the
              other: a manager who does rounds and an assistant on office duties
              are both ordinary.
            - Filtering here rather than in the repository is deliberate. A
              manager's workforce screen must still show everybody, and a query
              that quietly dropped the office staff would make them look
              dismissed.
        """
        schedulable = [person for person in workforce if person.field_employee]
        held_back = len(workforce) - len(schedulable)
        if held_back:
            self.logger.info(
                "%d of %d assistant(s) are not field employees and are left "
                "out of this run.",
                held_back,
                len(workforce),
            )
        if not schedulable:
            self.logger.warning(
                "No field employee is available: all %d assistant(s) are "
                "marked office-based, so nothing can be planned.",
                len(workforce),
            )
        return schedulable

    async def _get_run(self, run_id: str) -> PlanningRun:
        """Return a run or report that it does not exist.

        Args:
            run_id (str): The run to read.

        Returns:
            PlanningRun: The run.

        Raises:
            MTPlanningRunNotFound: If no such run exists.
        """
        run = await self.runs.get(run_id)
        if run is None:
            self.logger.warning("Planning run %s does not exist.", run_id)
            raise MTPlanningRunNotFound(f"No planning run {run_id!r} exists.")
        return run

    async def _claim(self, run: PlanningRun) -> Optional[PlanningRun]:
        """Take the run for this process, or report that somebody else has it.

        Args:
            run (PlanningRun): The run being executed.

        Returns:
            Optional[PlanningRun]: The run, now ``running``, or ``None`` when it
            was not pending and so belongs to another worker or is finished.

        Notes:
            - **The claim is a compare-and-swap in the database, not a status
              written over whatever was there.** Two workers can hold the same
              message — it is acknowledged only when its handler returns, so a
              worker killed mid-solve leaves the run to be redelivered — and
              before this, both would have solved the same period and each
              overwritten the other's plan.
            - Losing the race is an ordinary outcome. The caller returns the run
              untouched, the message is acknowledged, and the worker that won
              carries on.
        """
        self.logger.debug("Trying to claim planning run %s.", run.id)
        if run.id is None:
            self.logger.error("Cannot claim a planning run with no identifier.")
            return None
        claimed = await self.runs.claim(run.id, datetime.now(UTC))
        if claimed is None:
            self.logger.warning(
                "Planning run %s is already %s; leaving it to whoever holds it.",
                run.id,
                run.status.value,
            )
            return None
        self.logger.info("Planning run %s is running.", run.id)
        return claimed

    def _record_outcome(
        self,
        status: PlanningRunStatus,
        seconds: float,
        scheduled: Optional[int] = None,
    ) -> None:
        """Record how a run went, when anything is listening.

        Args:
            status (PlanningRunStatus): How it ended.
            seconds (float): How long it took, from the claim.
            scheduled (Optional[int]): How many visits it wrote, when it wrote
                any.

        Notes:
            Guarded rather than assumed, because the API constructs a service
            per request to answer a read and passes no metrics; only the worker
            does. A service with none records nothing rather than failing —
            losing a figure must not lose a plan.
        """
        if self.metrics is None:
            return
        self.metrics.record_run(status.value, seconds, scheduled)

    async def _solve(
        self, run: PlanningRun
    ) -> Tuple[PlanningSolution, List[InterventionRequirement], List[Hca]]:
        """Gather the inputs and run the solver off the event loop.

        Args:
            run (PlanningRun): The run being executed.

        Returns:
            Tuple[PlanningSolution, List[InterventionRequirement], List[Hca]]:
            The solution, the requirements it was built from, and the
            assistants it was solved over.

        Notes:
            The solver call goes through :func:`asyncio.to_thread`. CP-SAT is
            synchronous C++ and holds the calling thread for its whole budget;
            running it inline would freeze every other request in the process.
        """
        quotes = await self.quotes.list_schedulable(
            run.company_id, run.period_start, run.period_end
        )
        customers: Dict[str, Customer] = {}
        for quote in quotes:
            if quote.customer_id not in customers:
                customer = await self.customers.get(quote.customer_id)
                if customer is not None:
                    customers[quote.customer_id] = customer
        catalog = await self.types.get_many(
            [line.intervention_type_id for quote in quotes for line in quote.lines]
        )
        requirements = self.build(
            quotes, customers, catalog, run.period_start, run.period_end
        )
        assistants = self._field_employees(await self.hcas.list_all())
        self.build_travel(assistants, requirements)
        settings = await self.current_settings()

        self.logger.info(
            "Handing %d requirement(s) to the solver on a worker thread, with "
            "a %.1f km radius and a %d minute lunch break.",
            len(requirements),
            settings.max_intervention_radius_km,
            settings.lunch_break_minutes,
        )
        solution = await asyncio.to_thread(
            self.solve, requirements, assistants, settings
        )
        self._require_complete(solution, requirements, assistants, settings)
        return solution, requirements, assistants

    def _require_complete(
        self,
        solution: PlanningSolution,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
        settings: PlanningSettings,
    ) -> None:
        """Fail the run unless every piece of accepted work was placed.

        Args:
            solution (PlanningSolution): What the solver decided.
            requirements (List[InterventionRequirement]): The work submitted.
            assistants (List[Hca]): The workforce it was solved over.
            settings (PlanningSettings): The rules in force.

        Raises:
            MTPlanningInfeasible: If the solver could not satisfy the
                constraints for every requirement.

        Notes:
            - *A partial plan is refused, not stored.** A calendar missing three
              visits still looks like a calendar; nobody reads the run record to
              check, and the visits quietly dropped are the ones that end with a
              customer waiting at the door. Failing means this week's existing
              plan stays untouched — :meth:`_store` is never reached — so the
              agency keeps a working calendar while the problem is fixed.
            - The message names each visit and why it did not fit, so a manager
              can widen the radius, move a window or file cover without having to
              re-run anything to find out what went wrong.
        """
        if solution.is_feasible and not solution.unassigned_requirement_ids:
            self.logger.info("Every requirement was placed within the constraints.")
            return

        unplaced_ids = (
            solution.unassigned_requirement_ids
            if solution.unassigned_requirement_ids
            else [item.id for item in requirements]
        )
        explained = self.explain_unplaced(
            unplaced_ids, requirements, assistants, settings
        )
        # When the solver produced no plan at all, the per-visit reasons below
        # are not findings about those visits. `explain_unplaced` re-checks the
        # things it can decide on its own — the radius, the qualifications, the
        # working day — and falls through to `no-feasible-slot` for everything
        # else, which reads as "travel and lunch left no room". Nothing
        # established that. The search simply stopped, and saying otherwise
        # sends a manager to move windows and widen radii for a problem whose
        # answer is a bigger budget.
        specific = [
            item for item in explained if item.reason is not UnplacedReason.NO_FEASIBLE_SLOT
        ]
        # Recorded here rather than in the diagnosis, because this is the point
        # at which a visit is definitely not going to happen. `explain_unplaced`
        # is also called by the screen that asks "why?" about a past run, and
        # counting there would inflate the figure every time somebody looked.
        if self.metrics is not None:
            for item in explained:
                self.metrics.record_unplaced(item.reason.value)
        if not solution.is_feasible:
            self.logger.error(
                "The solver returned no plan at all (status %s) for %d "
                "requirement(s); %d of them have a specific obstacle and the "
                "rest were never individually diagnosed.",
                solution.status_name,
                len(requirements),
                len(specific),
            )
            raise MTPlanningInfeasible(self._describe_empty_solve(solution, specific))

        self.logger.error(
            "The planning constraints cannot be met: %d of %d requirement(s) "
            "could not be placed (solver status %s).",
            len(unplaced_ids),
            len(requirements),
            solution.status_name,
        )
        reasons = "; ".join(item.describe() for item in explained)
        raise MTPlanningInfeasible(
            f"The planning constraints cannot be met: "
            f"{len(unplaced_ids)} of {len(requirements)} visit(s) could not be "
            f"scheduled. {reasons}"
        )

    def _describe_empty_solve(
        self,
        solution: PlanningSolution,
        specific: List[UnplacedRequirement],
    ) -> str:
        """Say what a solve that produced nothing actually established.

        Args:
            solution (PlanningSolution): What the solver returned.
            specific (List[UnplacedRequirement]): The obstacles the diagnosis
                could establish on its own, if any.

        Returns:
            str: The message the run fails with.

        Notes:
            - **``INFEASIBLE`` and ``UNKNOWN`` are different answers and used to
              read identically.** The first is a proof that no plan exists; the
              second means the search stopped — on the deterministic budget or
              the wall-clock net — having proved nothing. Reporting both as "77
              visits could not be scheduled, travel and lunch left no room"
              blames a cause nobody established, and points the reader at the
              windows and the radius when the answer may simply be a larger
              budget.
            - The specific obstacles are still worth naming. A visit nobody
              holds the qualification for is a fact about that visit whatever
              the solver went on to do, and it is often the real reason a solve
              got nowhere.
        """
        found = (
            " " + "; ".join(item.describe() for item in specific) if specific else ""
        )
        if solution.status_name == "INFEASIBLE":
            return (
                f"No plan can satisfy these constraints (solver status "
                f"{solution.status_name}): the solver proved it, rather than "
                f"running out of time.{found}"
            )
        return (
            f"The solver found no plan within its budget (status "
            f"{solution.status_name}). That is not a proof that none exists — "
            f"the search stopped before it could decide. Raise "
            f"planning.solver_deterministic_budget, or reduce the week's work, "
            f"and run it again.{found}"
        )

    async def _store(
        self,
        run: PlanningRun,
        solution: PlanningSolution,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
    ) -> int:
        """Turn the solver's output into visits and replace the period's plan.

        Args:
            run (PlanningRun): The run that produced the solution.
            solution (PlanningSolution): What the solver decided.
            requirements (List[InterventionRequirement]): The work it placed.
            assistants (List[Hca]): The workforce it placed them with.

        Returns:
            int: How many visits were written.

        Notes:
            An assignment whose customer has no loadable address is dropped
            rather than allowed to abort the store. One unreachable customer
            must not cost the whole workforce its week — the visit is reported
            at ERROR and everything else is written.
        """
        self.logger.info(
            "Storing %d assignment(s) from planning run %s.",
            len(solution.assignments),
            run.id,
        )
        by_requirement = {item.id: item for item in requirements}
        by_assistant = {assistant.id: assistant for assistant in assistants}
        customer_addresses = await self._customer_addresses(requirements)

        visits: List[Intervention] = []
        for assignment in solution.assignments:
            requirement = by_requirement[assignment.requirement_id]
            assistant = by_assistant[assignment.hca_id]
            address = customer_addresses.get(requirement.customer_id)
            if address is None:
                self.logger.error(
                    "Dropping the visit %r for customer %s: no address could "
                    "be loaded for them.",
                    requirement.name,
                    requirement.customer_id,
                )
                continue
            visits.append(
                Intervention(
                    planning_run_id=run.id,
                    company_id=run.company_id,
                    name=requirement.name,
                    intervention_type_id=requirement.intervention_type_id,
                    quote_line_id=requirement.quote_line_id or requirement.id,
                    hca_id=assistant.id,
                    hca_full_name=assistant.full_name(),
                    customer_id=requirement.customer_id,
                    day=requirement.day,
                    start_time=self._to_time(assignment.start_minute),
                    end_time=self._to_time(assignment.end_minute),
                    address=address,
                )
            )
        if not visits:
            self.logger.warning(
                "Planning run %s placed nothing; every calendar from %s to %s "
                "will be blank.",
                run.id,
                run.period_start,
                run.period_end,
            )
        written = await self.interventions.replace_for_period(
            run.company_id, run.period_start, run.period_end, visits
        )
        self.logger.info("Planning run %s wrote %d visit(s).", run.id, written)
        return written

    async def _customer_addresses(
        self, requirements: List[InterventionRequirement]
    ) -> Dict[str, PostalAddress]:
        """Load the address of every customer with work in the plan.

        Args:
            requirements (List[InterventionRequirement]): The placed work.

        Returns:
            Dict[str, PostalAddress]: Each address, keyed by customer.

        Notes:
            Copied onto the visit rather than joined at read time, so a printed
            round keeps saying where the assistant was actually sent even if
            the customer later moves.
        """
        self.logger.debug(
            "Loading the addresses behind %d placed requirement(s).",
            len(requirements),
        )
        addresses: Dict[str, PostalAddress] = {}
        for requirement in requirements:
            if requirement.customer_id in addresses:
                continue
            customer = await self.customers.get(requirement.customer_id)
            if customer is None:
                self.logger.error(
                    "Customer %s has work in the plan but could not be loaded; "
                    "the visit for %r cannot be stored.",
                    requirement.customer_id,
                    requirement.name,
                )
                continue
            addresses[requirement.customer_id] = customer.address
        self.logger.debug("Loaded %d distinct address(es).", len(addresses))
        return addresses

    async def _finish(
        self,
        run: PlanningRun,
        status: PlanningRunStatus,
        travel_minutes: Optional[int] = None,
        scheduled_count: Optional[int] = None,
        unassigned: Optional[List[str]] = None,
        error_message: Optional[str] = None,
    ) -> PlanningRun:
        """Record a run's outcome.

        Args:
            run (PlanningRun): The run being finished.
            status (PlanningRunStatus): How it ended.
            travel_minutes (Optional[int]): Travel in the solution.
            scheduled_count (Optional[int]): How many visits were written.
            unassigned (Optional[List[str]]): What could not be placed.
            error_message (Optional[str]): Why it failed, when it did.

        Returns:
            PlanningRun: The finished run.
        """
        finished = run.model_copy(
            update={
                "status": status,
                "finished_at": datetime.now(UTC),
                "total_travel_minutes": travel_minutes,
                "scheduled_count": scheduled_count,
                "unassigned_requirement_ids": unassigned or [],
                "error_message": error_message,
            }
        )
        updated = await self.runs.update(finished)
        self.logger.info(
            "Planning run %s finished as %s: %s visit(s), %s unplanned.",
            run.id,
            status.value,
            scheduled_count if scheduled_count is not None else 0,
            len(unassigned) if unassigned else 0,
        )
        return updated if updated else finished

    def _to_time(self, minute_of_day: int) -> time:
        """Convert a minute of day back to a wall-clock time.

        Args:
            minute_of_day (int): Minutes from midnight.

        Returns:
            time: The clock time.
        """
        return time(hour=minute_of_day // 60, minute=minute_of_day % 60)

    def _nearest_home_km(
        self, requirement: InterventionRequirement, assistants: List[Hca]
    ) -> Optional[float]:
        """Return the distance from the closest assistant's home.

        Args:
            requirement (InterventionRequirement): The work being diagnosed.
            assistants (List[Hca]): The workforce.

        Returns:
            Optional[float]: The shortest home-to-work distance in kilometres,
            or ``None`` when no assistant has a resolved home.
        """
        distances = []
        for assistant in assistants:
            home = assistant.address.to_geo_point()
            if home is not None:
                distances.append(home.distance_km(requirement.location))
        if not distances:
            self.logger.warning(
                "No assistant has a resolved home. "
                "Distance cannot be measured."
            )
            return None
        return min(distances)

    def _reachable_assistants(
        self,
        requirement: InterventionRequirement,
        assistants: List[Hca],
        settings: PlanningSettings,
    ) -> List[Hca]:
        """Return the assistants within the radius of a piece of work.

        Args:
            requirement (InterventionRequirement): The work being diagnosed.
            assistants (List[Hca]): The workforce.
            settings (PlanningSettings): The rules in force.

        Returns:
            List[Hca]: Those close enough to be sent.
        """
        reachable = []
        for assistant in assistants:
            home = assistant.address.to_geo_point()
            if home is None:
                continue
            if settings.covers(home.distance_km(requirement.location)):
                reachable.append(assistant)
        return reachable

    def _clashing_visit(
        self,
        requirement: InterventionRequirement,
        requirements: List[InterventionRequirement],
    ) -> Optional[InterventionRequirement]:
        """Return a visit to the same customer whose window forces an overlap.

        Args:
            requirement (InterventionRequirement): The work being diagnosed.
            requirements (List[InterventionRequirement]): All the work.

        Returns:
            Optional[InterventionRequirement]: The clashing visit, if the two
            cannot both fit inside their shared window.

        Notes:
            A clash is not "the windows overlap" — two visits can share a
            window and still be scheduled back to back. It is that the window
            they share is too short to hold both, which is what makes them
            genuinely incompatible.
        """
        same_customer_day = [
            other
            for other in requirements
            if other.id != requirement.id
            and other.customer_id == requirement.customer_id
            and other.day == requirement.day
        ]
        for other in same_customer_day:
            span_start = min(requirement.window_start_minute, other.window_start_minute)
            span_end = max(requirement.window_end_minute, other.window_end_minute)
            if span_end - span_start < (
                requirement.duration_minutes + other.duration_minutes
            ):
                return other
        return None

    def _diagnose(
        self,
        requirement: InterventionRequirement,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
        settings: PlanningSettings,
    ) -> UnplacedRequirement:
        """Work out why one requirement could not be placed.

        Args:
            requirement (InterventionRequirement): The work being diagnosed.
            requirements (List[InterventionRequirement]): All the work.
            assistants (List[Hca]): The workforce.
            settings (PlanningSettings): The rules in force.

        Returns:
            UnplacedRequirement: The record naming the reason.

        Notes:
            - Each check answers a question the solver's model folds together, so
              the first one that applies is reported and the rest are not tested.
              A visit nobody can reach is also a visit with no feasible slot, but
              only the first reading tells anybody what to change.
            - **The certification test comes before anything geographical**, and
              narrows the workforce for every test after it. A visit nobody is
              qualified for is also a visit nobody within the radius can take;
              reporting the distance would send a manager to widen a radius that
              was never the problem, while "nobody here holds DEAES" names a
              hire, a training course, or a requirement that was wrong.
            - **The skill test follows it and narrows the same list further.**
              The order between the two is not arbitrary: a certification is
              obtained, a skill is merely declared, so a visit blocked by both
              is reported against the one that takes longer to fix. Running the
              skill test on the already-narrowed ``candidates`` is what makes
              that hold — starting again from the full workforce would report a
              skill gap for a visit whose real obstacle is a missing diploma.
        """
        if (
            requirement.window_start_minute < settings.day_start_minute
            or requirement.window_end_minute > settings.day_end_minute
        ):
            return UnplacedRequirement(
                requirement_id=requirement.id,
                name=requirement.name,
                customer_id=requirement.customer_id,
                day=requirement.day,
                reason=UnplacedReason.OUTSIDE_WORKING_DAY,
                detail=(
                    f"its window falls outside the "
                    f"{settings.describe_working_day()} working day"
                ),
            )

        candidates = assistants
        if requirement.requires_certifications():
            candidates = [
                assistant
                for assistant in assistants
                if assistant.holds_certifications(
                    requirement.required_certification_codes, requirement.day
                )
            ]
            if not candidates:
                return UnplacedRequirement(
                    requirement_id=requirement.id,
                    name=requirement.name,
                    customer_id=requirement.customer_id,
                    day=requirement.day,
                    reason=UnplacedReason.MISSING_CERTIFICATION,
                    detail=(
                        f"none of the {len(assistants)} field employee(s) holds "
                        f"{', '.join(requirement.required_certification_codes)} "
                        f"unexpired on {requirement.day}"
                    ),
                )

        if requirement.requires_skills():
            candidates = [
                assistant
                for assistant in candidates
                if assistant.holds_skills(
                    requirement.required_skill_codes, requirement.day
                )
            ]
            if not candidates:
                return UnplacedRequirement(
                    requirement_id=requirement.id,
                    name=requirement.name,
                    customer_id=requirement.customer_id,
                    day=requirement.day,
                    reason=UnplacedReason.MISSING_SKILL,
                    detail=(
                        f"none of the {len(assistants)} field employee(s) has "
                        f"declared "
                        f"{', '.join(requirement.required_skill_codes)} "
                        f"unexpired on {requirement.day}"
                    ),
                )

        reachable = self._reachable_assistants(requirement, candidates, settings)
        if not reachable:
            nearest = self._nearest_home_km(requirement, candidates)
            detail = (
                f"the nearest assistant lives {nearest:.1f} km away, beyond the "
                f"{settings.max_intervention_radius_km:.1f} km radius"
                if nearest is not None
                else "no assistant has a resolved home address"
            )
            return UnplacedRequirement(
                requirement_id=requirement.id,
                name=requirement.name,
                customer_id=requirement.customer_id,
                day=requirement.day,
                reason=UnplacedReason.OUT_OF_RADIUS,
                detail=detail,
            )

        working = [
            assistant
            for assistant in reachable
            if assistant.works_on_weekday(requirement.day)
        ]
        if not working:
            return UnplacedRequirement(
                requirement_id=requirement.id,
                name=requirement.name,
                customer_id=requirement.customer_id,
                day=requirement.day,
                reason=UnplacedReason.NOT_A_WORKING_DAY,
                detail=(
                    f"none of the {len(reachable)} assistant(s) within the "
                    f"radius works a "
                    f"{requirement.day.strftime('%A').lower()}"
                ),
            )

        if not [
            assistant
            for assistant in working
            if assistant.is_available_on(requirement.day)
        ]:
            return UnplacedRequirement(
                requirement_id=requirement.id,
                name=requirement.name,
                customer_id=requirement.customer_id,
                day=requirement.day,
                reason=UnplacedReason.NO_ASSISTANT_AVAILABLE,
                detail=(
                    f"all {len(working)} assistant(s) within the radius who "
                    f"work that day are absent on {requirement.day}"
                ),
            )

        clash = self._clashing_visit(requirement, requirements)
        if clash is not None:
            return UnplacedRequirement(
                requirement_id=requirement.id,
                name=requirement.name,
                customer_id=requirement.customer_id,
                day=requirement.day,
                reason=UnplacedReason.CUSTOMER_CONFLICT,
                detail=(
                    f"it cannot fit alongside {clash.name!r} for the same "
                    f"customer without the two overlapping"
                ),
            )

        return UnplacedRequirement(
            requirement_id=requirement.id,
            name=requirement.name,
            customer_id=requirement.customer_id,
            day=requirement.day,
            reason=UnplacedReason.NO_FEASIBLE_SLOT,
            detail=(
                "travel, the lunch break and the other visits that day leave "
                "no room for it"
            ),
        )

    def _unplaced_sort_key(self, item: UnplacedRequirement) -> Tuple[str, date, str]:
        """Return the ordering key grouping a report by reason.

        Args:
            item (UnplacedRequirement): The record to order.

        Returns:
            Tuple[str, date, str]: Reason, then day, then name.
        """
        return (item.reason.value, item.day, item.name)

    def _reset(self) -> None:
        """Discard any state from a previous solve.

        Notes:
            A solver instance is reusable, and leaving variables from a prior
            run in the tables would silently mix two problems together.
        """
        self.model = cp_model.CpModel()
        self.assigned = {}
        self.unassigned = {}
        self.starts = {}
        self.ends = {}
        self.intervals = {}
        self.placed_intervals = {}
        self.travel_terms = []

    def _by_day(
        self, requirements: List[InterventionRequirement]
    ) -> Dict[date, List[InterventionRequirement]]:
        """Group the requirements by the day they must happen on.

        Args:
            requirements (List[InterventionRequirement]): The work to group.

        Returns:
            Dict[date, List[InterventionRequirement]]: The work, day by day.
        """
        grouped: Dict[date, List[InterventionRequirement]] = defaultdict(list)
        for requirement in requirements:
            grouped[requirement.day].append(requirement)
        return dict(grouped)

    def _build_assignment_vars(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
    ) -> None:
        """Create the who-does-what booleans.

        Args:
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.

        Notes:
            Exactly one of "assistant A does it", ..., "nobody does it" holds
            for each requirement. Including the nobody option in the same
            equality is what makes the model always solvable.
        """
        for requirement in requirements:
            literals = []
            for assistant in assistants:
                literal = self.model.new_bool_var(
                    f"assign_{requirement.id}_{assistant.id}"
                )
                self.assigned[(requirement.id, assistant.id)] = literal
                literals.append(literal)
            dropped = self.model.new_bool_var(f"unassigned_{requirement.id}")
            self.unassigned[requirement.id] = dropped
            self.model.add_exactly_one(literals + [dropped])

    def _build_interval_vars(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
    ) -> None:
        """Create the when-does-it-happen variables.

        Args:
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.

        Notes:
            One start per requirement, shared by every assistant: the work
            happens at one time whoever does it. The per-assistant intervals
            are *optional*, present only when that assistant is assigned, which
            is what lets one no-overlap constraint per assistant see only their
            own round.
        """
        for requirement in requirements:
            start = self.model.new_int_var(
                requirement.window_start_minute,
                requirement.latest_start_minute(),
                f"start_{requirement.id}",
            )
            end = self.model.new_int_var(
                requirement.window_start_minute + requirement.duration_minutes,
                requirement.window_end_minute,
                f"end_{requirement.id}",
            )
            self.model.add(end == start + requirement.duration_minutes)
            self.starts[requirement.id] = start
            self.ends[requirement.id] = end
            for assistant in assistants:
                self.intervals[(requirement.id, assistant.id)] = (
                    self.model.new_optional_interval_var(
                        start,
                        requirement.duration_minutes,
                        end,
                        self.assigned[(requirement.id, assistant.id)],
                        f"interval_{requirement.id}_{assistant.id}",
                    )
                )

    def _add_day_bounds(self, requirements: List[InterventionRequirement]) -> None:
        """Keep every visit inside the working day.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Notes:
            - The window on a requirement comes from the customer; this is the
              agency's own rule — nothing before the day starts, nothing after it
              ends — and it applies on top.
            - **The bounds come from the stored settings, not the configuration
              file.** They are a manager's decision, like the radius and the
              break length, and reading them from ``app.yaml`` would have meant a
              deployment every time the agency moved its hours.
        """
        for requirement in requirements:
            self.model.add(
                self.starts[requirement.id] >= self.settings.day_start_minute
            )
            self.model.add(self.ends[requirement.id] <= self.settings.day_end_minute)

    def _add_availability(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
    ) -> None:
        """Refuse work to an assistant who does not work that day, or is away.

        Args:
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.

        Notes:
            - **Two separate things are enforced here, and both are hard.** A
              day the assistant never works — their recurring days off — and a
              dated whole-day absence both force the assignment literal to
              zero. The solver cannot pay its way past either.
            - A partial-day absence — a morning of training — is handled as a
              blocking interval in :meth:`_add_no_overlap` instead, so the rest
              of the day stays usable. There is no partial-day equivalent of a
              recurring day off: not working Wednesdays means the whole of it.
            - The conjunction lives on the model, in
              :meth:`~models.people.hca.Hca.is_schedulable_on`, so this
              constraint and the diagnosis in :meth:`_diagnose` cannot drift
              into disagreeing about who could have taken the visit.
            - An assistant whose home never geocoded is also refused everything:
              without a coordinate their round cannot be routed, and a plan built
              on a missing home is worse than one that leaves them free.
        """
        for assistant in assistants:
            if not assistant.address.is_geocoded():
                self.logger.warning(
                    "Assistant %s has no resolved home address; they cannot be "
                    "routed and will be given no work.",
                    assistant.id,
                )
                for requirement in requirements:
                    self.model.add(self.assigned[(requirement.id, assistant.id)] == 0)
                continue
            self.logger.debug(
                "Assistant %s works %d day(s) a week.",
                assistant.id,
                len(assistant.working_weekdays),
            )
            for requirement in requirements:
                if not assistant.is_schedulable_on(requirement.day):
                    self.model.add(self.assigned[(requirement.id, assistant.id)] == 0)

    def _add_certifications(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
    ) -> None:
        """Refuse work to an assistant who is not qualified for it.

        Args:
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.

        Notes:
            - **A hard constraint, not a preference.** An unqualified
              assistant's assignment literal is forced to zero, so the solver
              cannot pay its way past this the way it can pay for travel. If
              nobody qualifies, the requirement goes unassigned and the run
              fails — which is the intended answer: sending somebody
              unqualified is worse than sending nobody, and the failed run says
              which qualification was missing.
            - Requirements needing nothing are skipped entirely rather than
              given a constraint every assistant satisfies. Most work needs no
              qualification, and a satisfied-by-everybody constraint per visit
              per assistant would grow the model for no gain.
            - The expiry is judged on the **day of the visit**, inside
              :meth:`~models.people.hca.Hca.holds_certifications`. A plan built
              a fortnight ahead must not hand work to somebody whose
              certificate lapses before they get there.
        """
        gated = [item for item in requirements if item.requires_certifications()]
        if not gated:
            self.logger.debug("No requirement calls for a qualification.")
            return
        self.logger.info(
            "%d of %d requirement(s) call for a qualification.",
            len(gated),
            len(requirements),
        )
        for requirement in gated:
            qualified = [
                assistant
                for assistant in assistants
                if assistant.holds_certifications(
                    requirement.required_certification_codes, requirement.day
                )
            ]
            if not qualified:
                self.logger.error(
                    "No field employee holds %s on %s; %r cannot be placed.",
                    ", ".join(requirement.required_certification_codes),
                    requirement.day,
                    requirement.name,
                )
            elif len(qualified) < len(assistants):
                self.logger.debug(
                    "%d of %d assistant(s) may take %r on %s.",
                    len(qualified),
                    len(assistants),
                    requirement.name,
                    requirement.day,
                )
            allowed = {assistant.id for assistant in qualified}
            for assistant in assistants:
                if assistant.id not in allowed:
                    self.model.add(self.assigned[(requirement.id, assistant.id)] == 0)

    def _add_skills(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
    ) -> None:
        """Refuse work to an assistant who has not declared the skill it needs.

        Args:
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.

        Notes:
            - **A hard constraint, exactly like the certification one.** An
              assistant who has not declared the skill has their assignment
              literal forced to zero, so the solver cannot pay its way past it.
              If nobody qualifies the requirement goes unassigned and the run
              fails — which is the intended answer: sending somebody who cannot
              use a hoist to a visit that needs one is worse than sending
              nobody.
            - A **separate** constraint from :meth:`_add_certifications` rather
              than one loop over both lists. The two produce the same literals
              and an identical plan, so merging them would cost nothing at
              solve time — what it would cost is the log line below and the
              distinct unplaced reason, which is the only thing that tells a
              manager whether to arrange training or to ask somebody to finish
              their profile.
            - Requirements needing no skill are skipped entirely, which is most
              of them. The economy matters more here than for certifications:
              this is the second pass over the same work.
            - The expiry is judged on the **day of the visit**, inside
              :meth:`~models.people.hca.Hca.holds_skills`.
        """
        gated = [item for item in requirements if item.requires_skills()]
        if not gated:
            self.logger.debug("No requirement calls for a declared skill.")
            return
        self.logger.info(
            "%d of %d requirement(s) call for a declared skill.",
            len(gated),
            len(requirements),
        )
        for requirement in gated:
            qualified = [
                assistant
                for assistant in assistants
                if assistant.holds_skills(
                    requirement.required_skill_codes, requirement.day
                )
            ]
            if not qualified:
                self.logger.error(
                    "No field employee has declared %s on %s; %r cannot be "
                    "placed.",
                    ", ".join(requirement.required_skill_codes),
                    requirement.day,
                    requirement.name,
                )
            elif len(qualified) < len(assistants):
                self.logger.debug(
                    "%d of %d assistant(s) have declared what %r needs on %s.",
                    len(qualified),
                    len(assistants),
                    requirement.name,
                    requirement.day,
                )
            allowed = {assistant.id for assistant in qualified}
            for assistant in assistants:
                if assistant.id not in allowed:
                    self.model.add(self.assigned[(requirement.id, assistant.id)] == 0)

    def _add_radius(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
    ) -> None:
        """Forbid sending an assistant beyond the configured radius from home.

        Args:
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.

        Notes:
            - Measured from the assistant's **own home** to the work, not between
              consecutive visits. That is what the rule protects: an assistant is
              asked to cover an area around where they live, and a round that
              merely hops between neighbouring customers can still end fifty
              kilometres from home.
            - Expressed by fixing the assignment literal to zero rather than by
              penalising distance in the objective. A penalty is a preference and
              can be outweighed; this is a limit, and a plan that breaks it is not
              a worse plan but an invalid one.
            - An assistant whose home never resolved is excluded from every
              requirement. Their distance is unknowable, and assuming it is within
              the radius would route somebody from a place nobody can find.
        """
        radius_km = self.settings.max_intervention_radius_km
        self.logger.debug(
            "Applying a %.1f km intervention radius to %d requirement(s).",
            radius_km,
            len(requirements),
        )
        blocked = 0
        for assistant in assistants:
            home = assistant.address.to_geo_point()
            for requirement in requirements:
                if home is None:
                    self.model.add(self.assigned[(requirement.id, assistant.id)] == 0)
                    blocked += 1
                    continue
                distance_km = home.distance_km(requirement.location)
                if not self.settings.covers(distance_km):
                    self.logger.debug(
                        "Assistant %s is %.1f km from %r, beyond the %.1f km radius.",
                        assistant.id,
                        distance_km,
                        requirement.name,
                        radius_km,
                    )
                    self.model.add(self.assigned[(requirement.id, assistant.id)] == 0)
                    blocked += 1
        if blocked:
            self.logger.info(
                "The %.1f km radius rules out %d assistant-requirement pair(s).",
                radius_km,
                blocked,
            )

    def _add_customer_conflicts(
        self, requirements: List[InterventionRequirement]
    ) -> None:
        """Stop a customer receiving two visits at once.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Notes:
            - **This constraint spans assistants, which is why it cannot ride on
              the per-assistant no-overlap.** That one stops one assistant being
              in two places; nothing in it stops two *different* assistants being
              sent to the same customer's living room at the same hour. For a
              home-care agency that is the visible failure: the customer opens the
              door twice, and one of the two visits was never needed.
            - Each requirement gets a single interval, present exactly when
              somebody takes it, built on the start and end variables the
              per-assistant intervals already share. Grouping those by customer
              and day gives the constraint directly.
            - Requirements for the same customer on different days cannot clash,
              so the grouping is by both — pairing every visit a customer receives
              all week would add constraints that can never bind.
        """
        for requirement in requirements:
            self.placed_intervals[requirement.id] = (
                self.model.new_optional_interval_var(
                    self.starts[requirement.id],
                    requirement.duration_minutes,
                    self.ends[requirement.id],
                    self.unassigned[requirement.id].negated(),
                    f"placed_{requirement.id}",
                )
            )

        grouped: Dict[Tuple[str, date], List[InterventionRequirement]] = defaultdict(
            list
        )
        for requirement in requirements:
            grouped[(requirement.customer_id, requirement.day)].append(requirement)

        for (customer_id, day), same_day in grouped.items():
            if len(same_day) < 2:
                continue
            self.logger.debug(
                "Customer %s has %d visit(s) on %s; forbidding any overlap.",
                customer_id,
                len(same_day),
                day,
            )
            self.model.add_no_overlap(
                [self.placed_intervals[item.id] for item in same_day]
            )

    def _add_no_overlap(
        self,
        assistant: Hca,
        day: date,
        requirements: List[InterventionRequirement],
    ) -> None:
        """Stop an assistant being in two places at once.

        Args:
            assistant (Hca): The assistant whose day is being constrained.
            day (date): The day in question.
            requirements (List[InterventionRequirement]): That day's work.

        Notes:
            Partial-day absences join the same constraint as fixed intervals,
            so a training session blocks its hours exactly as a visit would.
        """
        intervals = [
            self.intervals[(requirement.id, assistant.id)]
            for requirement in requirements
        ]
        for slot in assistant.blocking_slots_on(day):
            start_minute = slot.start_time.hour * 60 + slot.start_time.minute
            end_minute = slot.end_time.hour * 60 + slot.end_time.minute
            intervals.append(
                self.model.new_interval_var(
                    start_minute,
                    end_minute - start_minute,
                    end_minute,
                    f"absence_{assistant.id}_{day}_{start_minute}",
                )
            )
        self.model.add_no_overlap(intervals)

    def _add_lunch_break(
        self,
        assistant: Hca,
        day: date,
        requirements: List[InterventionRequirement],
    ) -> None:
        """Reserve an uninterrupted lunch break in the middle of the day.

        Args:
            assistant (Hca): The assistant whose day is being constrained.
            day (date): The day in question.
            requirements (List[InterventionRequirement]): That day's work.

        Notes:
            - The break is a real interval competing with the visits for the same
              no-overlap resource, not a gap the solver is asked to leave. That
              is what makes it uninterrupted: nothing can be scheduled across it,
              because it occupies the time.
            - It is *optional*, present only when the assistant actually works
              that day. A mandatory break would otherwise constrain the days they
              are not working at all, and on a day with no feasible slot would
              make the whole day infeasible rather than merely unassigned.
            - Its length *and its window* come from the stored settings, not the
              configuration file: the business requires both to be
              configurable, and a manager changing either must not need a
              deployment. The settings model refuses a window too narrow to
              hold the break, so the lower bound below cannot exceed the upper.
        """
        works_today = self.model.new_bool_var(f"works_{assistant.id}_{day}")
        assignment_literals = [
            self.assigned[(requirement.id, assistant.id)]
            for requirement in requirements
        ]
        self.model.add_max_equality(works_today, assignment_literals)

        break_start = self.model.new_int_var(
            self.settings.lunch_window_start_minute,
            self.settings.lunch_window_end_minute - self.settings.lunch_break_minutes,
            f"lunch_start_{assistant.id}_{day}",
        )
        break_interval = self.model.new_optional_interval_var(
            break_start,
            self.settings.lunch_break_minutes,
            break_start + self.settings.lunch_break_minutes,
            works_today,
            f"lunch_{assistant.id}_{day}",
        )
        intervals = [
            self.intervals[(requirement.id, assistant.id)]
            for requirement in requirements
        ]
        self.model.add_no_overlap(intervals + [break_interval])

    def _add_travel(
        self,
        assistant: Hca,
        day: date,
        requirements: List[InterventionRequirement],
    ) -> None:
        """Leave time to get between consecutive visits, and cost the journeys.

        Args:
            assistant (Hca): The assistant whose round is being constrained.
            day (date): The day in question.
            requirements (List[InterventionRequirement]): That day's work.

        Notes:
            - Each unordered pair gets two ordering literals, and when the
              assistant holds both visits **exactly one of them must be true**.
              That forced choice is the whole mechanism: an earlier version only
              said "ordering implies assignment", which let the solver leave both
              literals false, skip the separation constraint and pay no travel —
              so consecutive visits could legally start the instant the previous
              one ended, wherever they were.
            - Each visit is then either the first of the round or preceded by
              exactly one other, and either the last or followed by exactly one.
              Those two flags are what make the home legs honest: the journey
              from home is charged once, to the first visit, and the journey back
              once, from the last — rather than to every visit in the round.
            - Pairwise rather than a single circuit constraint. A circuit is
              tighter, but it has to be built over a fixed node set, and here the
              node set is itself a decision — a visit may end up unassigned. The
              cost is a larger model on dense days, which the solver's time limit
              bounds.
        """
        routable = assistant.id in self.travel_minutes
        home = assistant.address.to_geo_point()
        if not routable or home is None:
            self.logger.warning(
                "No travel information for assistant %s; their round is being "
                "planned with no travel time at all.",
                assistant.id,
            )
            return
        self.logger.debug(
            "Adding travel constraints for assistant %s over %d visit(s).",
            assistant.id,
            len(requirements),
        )

        before: Dict[Tuple[str, str], cp_model.IntVar] = {}
        for index, first in enumerate(requirements):
            for second in requirements[index + 1 :]:
                before.update(self._order_pair(assistant, first, second))
        for requirement in requirements:
            self._add_home_legs(assistant, requirement, requirements, before, home)

    def _order_pair(
        self,
        assistant: Hca,
        first: InterventionRequirement,
        second: InterventionRequirement,
    ) -> Dict[Tuple[str, str], cp_model.IntVar]:
        """Force an order on two visits the same assistant might hold.

        Args:
            assistant (Hca): The assistant in question.
            first (InterventionRequirement): One visit.
            second (InterventionRequirement): The other.

        Returns:
            Dict[Tuple[str, str], cp_model.IntVar]: The two ordering literals,
            keyed by the ordered pair they represent.

        Notes:
            When the assistant holds both, exactly one ordering holds and the
            corresponding journey is both enforced and charged. When they hold
            at most one, neither ordering holds and no travel is charged.
        """
        holds_first = self.assigned[(first.id, assistant.id)]
        holds_second = self.assigned[(second.id, assistant.id)]
        holds_both = self.model.new_bool_var(
            f"both_{assistant.id}_{first.id}_{second.id}"
        )
        self.model.add_bool_and([holds_first, holds_second]).only_enforce_if(holds_both)
        self.model.add_bool_or(
            [holds_first.negated(), holds_second.negated(), holds_both]
        )

        first_then_second = self.model.new_bool_var(
            f"before_{assistant.id}_{first.id}_{second.id}"
        )
        second_then_first = self.model.new_bool_var(
            f"before_{assistant.id}_{second.id}_{first.id}"
        )
        self.model.add(first_then_second + second_then_first == 1).only_enforce_if(
            holds_both
        )
        self.model.add(first_then_second + second_then_first == 0).only_enforce_if(
            holds_both.negated()
        )

        forward = self.travel_between_points(
            assistant.id, first.location, second.location
        )
        backward = self.travel_between_points(
            assistant.id, second.location, first.location
        )
        self.model.add(
            self.starts[second.id] >= self.ends[first.id] + forward
        ).only_enforce_if(first_then_second)
        self.model.add(
            self.starts[first.id] >= self.ends[second.id] + backward
        ).only_enforce_if(second_then_first)
        self.travel_terms.append(forward * first_then_second)
        self.travel_terms.append(backward * second_then_first)

        return {
            (first.id, second.id): first_then_second,
            (second.id, first.id): second_then_first,
        }

    def _add_home_legs(
        self,
        assistant: Hca,
        requirement: InterventionRequirement,
        requirements: List[InterventionRequirement],
        before: Dict[Tuple[str, str], cp_model.IntVar],
        home: GeoPoint,
    ) -> None:
        """Charge the journey from home to the round, and back from it.

        Args:
            assistant (Hca): The assistant whose round it is.
            requirement (InterventionRequirement): The visit being considered.
            requirements (List[InterventionRequirement]): That day's work.
            before (Dict[Tuple[str, str], cp_model.IntVar]): The ordering
                literals for the day.
            home (GeoPoint): Where the assistant lives.

        Notes:
            A visit with no predecessor is the first of the round, and one with
            no successor is the last. Charging the home legs to those two — and
            requiring the first not to start before the assistant could have
            driven there — is what makes an assistant living among their
            customers genuinely cheaper than one commuting across the city.
        """
        holds = self.assigned[(requirement.id, assistant.id)]
        predecessors = [
            before[(other.id, requirement.id)]
            for other in requirements
            if other.id != requirement.id
        ]
        successors = [
            before[(requirement.id, other.id)]
            for other in requirements
            if other.id != requirement.id
        ]

        is_first = self.model.new_bool_var(f"first_{assistant.id}_{requirement.id}")
        is_last = self.model.new_bool_var(f"last_{assistant.id}_{requirement.id}")
        self.model.add(sum(predecessors) == 0).only_enforce_if([holds, is_first])
        self.model.add(sum(predecessors) >= 1).only_enforce_if(
            [holds, is_first.negated()]
        )
        self.model.add(sum(successors) == 0).only_enforce_if([holds, is_last])
        self.model.add(sum(successors) >= 1).only_enforce_if([holds, is_last.negated()])
        self.model.add(is_first == 0).only_enforce_if(holds.negated())
        self.model.add(is_last == 0).only_enforce_if(holds.negated())

        outbound = self.travel_between_points(assistant.id, home, requirement.location)
        inbound = self.travel_between_points(assistant.id, requirement.location, home)
        self.travel_terms.append(outbound * is_first)
        self.travel_terms.append(inbound * is_last)
        self.model.add(
            self.starts[requirement.id] >= self.settings.day_start_minute + outbound
        ).only_enforce_if(is_first)

    def _add_objective(self, requirements: List[InterventionRequirement]) -> None:
        """Minimise travel, and treat dropping work as very expensive.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Notes:
            The unassigned penalty must dominate any realistic travel cost, or
            the solver would discover that leaving a distant visit out is
            cheaper than driving to it — technically optimal, commercially
            absurd.
        """
        dropped_cost = [
            self.config.unassigned_penalty * self.unassigned[requirement.id]
            for requirement in requirements
        ]
        travel_cost = [self.config.travel_weight * term for term in self.travel_terms]
        self.model.minimize(sum(dropped_cost) + sum(travel_cost))

    def _run(self, requirements: List[InterventionRequirement]) -> PlanningSolution:
        """Search for a solution and read it back.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Returns:
            PlanningSolution: What was found.

        Notes:
            - The time limit is what makes this bounded work rather than an open
              question. An optimal answer is preferred, but a good feasible one
              inside the budget is what a planning screen actually needs.
            - **The search is made reproducible on purpose.** Re-planning the
              same week used to give a different answer every time — 77 visits
              at 404 minutes of travel, then 371, then 355 — because a
              wall-clock budget stops the search wherever it happens to have
              got to, and parallel workers race each other to the incumbent.
              A manager who reruns a plan and sees three different numbers has
              no way to tell an improvement from noise, and no way to tell
              whether the quote they just accepted changed anything.
            - Three things together make it reproducible, and **a fixed seed
              alone was not enough** — that was tried first and still gave
              502, 495, 502 minutes across three runs of one input.
              ``random_seed`` fixes the tie-breaking; ``num_search_workers``
              of one stops parallel workers racing to the incumbent; and
              ``max_deterministic_time`` is what actually stops the search at
              the same place every time. A wall-clock budget cannot: it halts
              wherever elapsed time happens to land, so a loaded machine
              explores less and returns a worse plan for the same week.
            - The wall-clock limit is kept as a **safety net, not a budget**.
              Deterministic time is a measure of work rather than of seconds,
              so a pathological instance could grind for a very long time
              inside its allowance; the clock bounds that. If it ever fires
              the run is no longer reproducible, and it says so at WARNING —
              a plan that silently stopped being comparable is worse than one
              that admits it.
        """
        solver = cp_model.CpSolver()
        solver.parameters.max_deterministic_time = (
            self.config.solver_deterministic_budget
        )
        solver.parameters.max_time_in_seconds = self.config.solver_time_limit_seconds
        solver.parameters.num_search_workers = self.config.solver_workers
        solver.parameters.random_seed = self.config.solver_seed
        self.logger.info(
            "Solving with a deterministic budget of %.1f, a %.1fs safety net, "
            "%d worker(s) and seed %d.",
            self.config.solver_deterministic_budget,
            self.config.solver_time_limit_seconds,
            self.config.solver_workers,
            self.config.solver_seed,
        )
        status = solver.solve(self.model)
        status_name = solver.status_name(status)
        if solver.wall_time >= self.config.solver_time_limit_seconds:
            self.logger.warning(
                "The solve hit its %.1fs wall-clock safety net rather than its "
                "deterministic budget; this plan is not reproducible, and the "
                "same week may plan differently next time.",
                self.config.solver_time_limit_seconds,
            )

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # INFEASIBLE is a proof; UNKNOWN is a search that stopped. Saying
            # "contradictory" for both told an operator the constraints were
            # impossible when the honest answer was that the budget ran out.
            if status == cp_model.INFEASIBLE:
                self.logger.error(
                    "The solver proved no plan exists (%s); the constraints are "
                    "contradictory rather than merely tight.",
                    status_name,
                )
            else:
                self.logger.error(
                    "The solver found no plan within its budget (%s) after "
                    "%.1fs. Nothing was proved about feasibility — the search "
                    "stopped. A larger planning.solver_deterministic_budget, or "
                    "less work in the period, is the lever.",
                    status_name,
                    solver.wall_time,
                )
            return PlanningSolution(
                unassigned_requirement_ids=[item.id for item in requirements],
                is_feasible=False,
                status_name=status_name,
            )
        return self._extract(solver, requirements, status_name)

    def _extract(
        self,
        solver: cp_model.CpSolver,
        requirements: List[InterventionRequirement],
        status_name: str,
    ) -> PlanningSolution:
        """Turn the solver's variable values into a solution.

        Args:
            solver (cp_model.CpSolver): The solved solver.
            requirements (List[InterventionRequirement]): The work.
            status_name (str): The solver's status, for the record.

        Returns:
            PlanningSolution: The plan.
        """
        assignments: List[ScheduledAssignment] = []
        unassigned: List[str] = []
        for requirement in requirements:
            if solver.value(self.unassigned[requirement.id]):
                unassigned.append(requirement.id)
                continue
            assignments.append(
                ScheduledAssignment(
                    requirement_id=requirement.id,
                    hca_id=self._assignee(solver, requirement),
                    start_minute=solver.value(self.starts[requirement.id]),
                    end_minute=solver.value(self.ends[requirement.id]),
                )
            )
        travel = sum(solver.value(term) for term in self.travel_terms)
        if unassigned:
            self.logger.warning(
                "%d of %d requirement(s) could not be placed: %s.",
                len(unassigned),
                len(requirements),
                ", ".join(unassigned),
            )
        self.logger.info(
            "Planned %d requirement(s) with %d minute(s) of travel (%s).",
            len(assignments),
            travel,
            status_name,
        )
        return PlanningSolution(
            assignments=assignments,
            unassigned_requirement_ids=unassigned,
            total_travel_minutes=int(travel),
            is_feasible=True,
            status_name=status_name,
        )

    def _assignee(
        self, solver: cp_model.CpSolver, requirement: InterventionRequirement
    ) -> str:
        """Return which assistant the solver gave a requirement to.

        Args:
            solver (cp_model.CpSolver): The solved solver.
            requirement (InterventionRequirement): The placed requirement.

        Returns:
            str: The assistant's identifier.

        Raises:
            MTPlanningInconsistentSolution: If no assistant holds it, which
                the exactly-one constraint makes impossible.
        """
        for (requirement_id, hca_id), literal in self.assigned.items():
            if requirement_id == requirement.id and solver.value(literal):
                return hca_id
        self.logger.error(
            "Requirement %s is neither assigned nor unassigned; the "
            "exactly-one constraint did not hold.",
            requirement.id,
        )
        raise MTPlanningInconsistentSolution(
            f"Requirement {requirement.id!r} is neither assigned nor dropped; "
            f"the exactly-one constraint was violated."
        )

    def _deduplicate(self, points: List[GeoPoint]) -> List[GeoPoint]:
        """Return the distinct places, in first-seen order.

        Args:
            points (List[GeoPoint]): The places to reduce.

        Returns:
            List[GeoPoint]: The distinct places.

        Notes:
            Order is preserved rather than sorted, so a resolver built twice
            from the same input indexes the same way — which keeps a solve
            reproducible.
        """
        seen: Dict[Tuple[float, float], GeoPoint] = {}
        for point in points:
            seen.setdefault((point.latitude, point.longitude), point)
        return list(seen.values())

    def _estimate_minutes(
        self, average_speed_kmh: float, origin: GeoPoint, destination: GeoPoint
    ) -> int:
        """Return the estimated travel time between two points, in minutes.

        Args:
            origin (GeoPoint): Where the journey starts.
            destination (GeoPoint): Where it ends.

        Returns:
            int: The estimate, rounded up. ``0`` only when the two points are
            identical.

        Notes:
            Rounded **up**. Rounding down would let the solver believe a
            back-to-back pair is feasible when it is a minute short, and a
            planning that is a minute optimistic at every hop is one an
            assistant cannot keep.
        """
        distance_km = origin.distance_km(destination)
        return math.ceil(distance_km / average_speed_kmh * 60)

    def _build_travel_table(
        self, average_speed_kmh: float, points: List[GeoPoint]
    ) -> Dict[Tuple[int, int], int]:
        """Compute the travel time between every ordered pair of places.

        Returns:
            Dict[Tuple[int, int], int]: The travel time for each pair.
        """
        self.logger.debug("Computing %d travel time(s).", len(points) ** 2)
        minutes: Dict[Tuple[int, int], int] = {}
        for origin_index, origin in enumerate(points):
            for destination_index, destination in enumerate(points):
                if origin_index == destination_index:
                    minutes[(origin_index, destination_index)] = 0
                    continue
                minutes[(origin_index, destination_index)] = self._estimate_minutes(
                    average_speed_kmh, origin, destination
                )
        return minutes

    def _to_minutes(self, clock_time: time) -> int:
        """Convert a wall-clock time to minutes from midnight.

        Args:
            clock_time (time): The time to convert.

        Returns:
            int: The minute of day.

        Notes:
            The solver's variables are integer minutes, so the conversion
            happens once here rather than at every constraint.
        """
        return clock_time.hour * 60 + clock_time.minute

    ############################
    # Publicly Exposed Methods #
    ############################

    def build_travel(
        self,
        assistants: List[Hca],
        requirements: List[InterventionRequirement],
    ) -> List[str]:
        """Compute one travel table per assistant, each at their own speed.

        Args:
            assistants (List[Hca]): The workforce.
            requirements (List[InterventionRequirement]): The work.

        Returns:
            List[str]: The identifiers of the assistants that can be routed.

        Notes:
            - One table each rather than one shared: an assistant with a driving
              licence covers ground far faster than one on public transport, and
              a single one would have to assume the same speed for everyone.
            - The tables are held on this service, keyed by assistant, and
              rebuilt at the start of every solve. One service instance serves
              one run — it is constructed per request — so there is no second
              solve to collide with.
            - Coordinates are de-duplicated first: several customers in one
              apartment block share a point, and pairs grow with the square of
              the count.
            - Both directions are computed rather than mirrored. A straight-line
              estimate is symmetric, but a road-based one is not, and assuming
              symmetry would quietly produce wrong routes the day the estimate
              is replaced.
        """
        self.logger.debug(
            "Building travel tables for %d assistant(s) over %d place(s).",
            len(assistants),
            len(requirements),
        )
        self.travel_points = {}
        self.travel_indexes = {}
        self.travel_minutes = {}
        points = [requirement.location for requirement in requirements]
        routable: List[str] = []
        for assistant in assistants:
            home = assistant.address.to_geo_point()
            if home is None:
                self.logger.warning(
                    "Assistant %s (%s) has no resolved home address (%s); they "
                    "cannot be routed and will be given no work.",
                    assistant.id,
                    assistant.full_name(),
                    assistant.address.geocoding_error,
                )
                continue
            speed = self.config.speed_for(assistant.can_drive())
            if speed <= 0:
                self.logger.error(
                    "Refusing to build a travel table for assistant %s at %r km/h.",
                    assistant.id,
                    speed,
                )
                raise MTPlanningInvalidSpeed(
                    f"Invalid travel speed for assistant {assistant.id!r}: "
                    f"{speed!r}. Must be strictly positive."
                )
            distinct = self._deduplicate(points + [home])
            self.travel_points[assistant.id] = distinct
            self.travel_indexes[assistant.id] = {
                (point.latitude, point.longitude): index
                for index, point in enumerate(distinct)
            }
            self.travel_minutes[assistant.id] = self._build_travel_table(
                speed, distinct
            )
            routable.append(assistant.id)
        if not routable:
            self.logger.error(
                "No assistant has a resolved home address; nothing can be "
                "planned until at least one does."
            )
        else:
            self.logger.info(
                "Travel tables built for %d of %d assistant(s).",
                len(routable),
                len(assistants),
            )
        return routable

    async def current_settings(self) -> PlanningSettings:
        """Return the rules in force, seeding them if this is the first read.

        Returns:
            PlanningSettings: The rules.

        Raises:
            MTPlanningSettingsUnavailable: If the rules can be neither read nor
                seeded.

        Notes:
            - Every read goes through here, which seeds from configuration when
              nothing is stored. That keeps the planner working on a fresh
              install, before anybody has opened the settings screen, without
              leaving a nullable "no rules yet" state for every caller to
              handle.
            - The configured values are a *seed*, not a fallback: once the row
              exists, editing ``app.yaml`` changes nothing. Treating the file as
              a live fallback would let a redeployment silently overwrite a
              manager's decision.
        """
        stored = await self.settings.get()
        if stored is not None:
            self.logger.debug(
                "Planning settings in force: radius %.1f km, working day %s, "
                "lunch %d min.",
                stored.max_intervention_radius_km,
                stored.describe_working_day(),
                stored.lunch_break_minutes,
            )
            return stored

        self.logger.info("No planning settings stored; seeding from configuration.")
        seeded = await self.settings.seed(
            PlanningSettings(
                max_intervention_radius_km=self.config.max_intervention_radius_km,
                day_start_minute=self.config.day_start_minute,
                day_end_minute=self.config.day_end_minute,
                lunch_break_minutes=self.config.lunch_break_minutes,
                lunch_window_start_minute=self.config.lunch_window_start_minute,
                lunch_window_end_minute=self.config.lunch_window_end_minute,
            )
        )
        if seeded is None:
            self.logger.error(
                "The planning settings could not be seeded; the planner has no "
                "rules to work from."
            )
            raise MTPlanningSettingsUnavailable(
                "The planning settings could not be read or seeded."
            )
        return seeded

    async def update_settings(
        self,
        max_intervention_radius_km: float,
        lunch_break_minutes: int,
        updated_by: str,
        day_start_minute: int,
        day_end_minute: int,
        lunch_window_start_minute: int,
        lunch_window_end_minute: int,
    ) -> PlanningSettings:
        """Change the rules.

        Args:
            max_intervention_radius_km (float): The new radius, in kilometres.
            lunch_break_minutes (int): The new break length, in minutes.
            updated_by (str): The account making the change.
            day_start_minute (int): Earliest minute a visit may start.
            day_end_minute (int): Latest minute a visit may end.
            lunch_window_start_minute (int): Earliest minute the break may
                start.
            lunch_window_end_minute (int): Latest minute the break may end.

        Returns:
            PlanningSettings: The rules now in force.

        Raises:
            MTPlanningSettingsUnavailable: If the rules cannot be written.

        Notes:
            - Reads first, so an update before the first read seeds rather than
              failing — a manager opening the settings screen on a fresh install
              should be able to change them straight away.
            - A change does not re-plan anything. The rules take effect on the
              next planning run, which is deliberate: silently rewriting this
              week's calendars because somebody adjusted a radius would move
              assistants who have already been told where to go.
        """
        await self.current_settings()
        updated = await self.settings.update(
            PlanningSettings(
                max_intervention_radius_km=max_intervention_radius_km,
                day_start_minute=day_start_minute,
                day_end_minute=day_end_minute,
                lunch_break_minutes=lunch_break_minutes,
                lunch_window_start_minute=lunch_window_start_minute,
                lunch_window_end_minute=lunch_window_end_minute,
                updated_by=updated_by,
                updated_at=datetime.now(UTC),
            )
        )
        if updated is None:
            self.logger.error(
                "The planning settings vanished between the read and the write."
            )
            raise MTPlanningSettingsUnavailable(
                "The planning settings could not be updated."
            )
        self.logger.warning(
            "Planning settings changed by %s: radius %.1f km, working day %s, "
            "lunch %d min. They apply to the next planning run, not to plans "
            "already made.",
            updated_by,
            updated.max_intervention_radius_km,
            updated.describe_working_day(),
            updated.lunch_break_minutes,
        )
        return updated

    def explain_unplaced(
        self,
        unplaced_ids: List[str],
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
        settings: PlanningSettings,
    ) -> List[UnplacedRequirement]:
        """Explain every piece of work the solver could not place.

        Args:
            unplaced_ids (List[str]): The requirements left unassigned.
            requirements (List[InterventionRequirement]): All the work.
            assistants (List[Hca]): The workforce.
            settings (PlanningSettings): The rules in force.

        Returns:
            List[UnplacedRequirement]: One record per unplaced requirement,
            grouped by reason so the report reads as a list of problems rather
            than a list of visits.

        Notes:
            - The solver can only report *that* something did not fit. This
              works out *why*, by testing the specific reasons in order of how
              actionable they are — a manager told "no assistant lives within
              30 km of Mme Durand" can widen the radius or hire; a manager told
              "INFEASIBLE" can do nothing.
            - This runs **after** a failed solve, never before one. It is a
              diagnosis, not a pre-flight gate: the tests here are necessary
              conditions, and something that passes all of them can still be
              unplaceable for reasons only the search can find.
        """
        self.logger.info("Diagnosing %d unplaced requirement(s).", len(unplaced_ids))
        by_id = {item.id: item for item in requirements}
        explained: List[UnplacedRequirement] = []
        for requirement_id in unplaced_ids:
            requirement = by_id.get(requirement_id)
            if requirement is None:
                self.logger.error(
                    "The solver reported %s unplaced, but no such requirement "
                    "was submitted.",
                    requirement_id,
                )
                continue
            explained.append(
                self._diagnose(requirement, requirements, assistants, settings)
            )

        counts: Dict[UnplacedReason, int] = defaultdict(int)
        for item in explained:
            counts[item.reason] += 1
        for reason, count in counts.items():
            self.logger.warning(
                "%d requirement(s) unplaced because: %s.", count, reason.value
            )
        return sorted(explained, key=self._unplaced_sort_key)

    async def future_period_for_hca(self, hca_id: str) -> Optional[Tuple[date, date]]:
        """Return the span of an assistant's remaining visits, from today.

        Args:
            hca_id (str): The assistant whose work is being measured.

        Returns:
            Optional[Tuple[date, date]]: The first and last day they are
            planned on from today onward, or ``None`` when they have no work
            left.

        Notes:
            "Today" is resolved here rather than passed in, so every caller
            asking "what does removing this person disturb?" gets the same
            answer. Days already past are excluded because they have already
            happened; rewriting them would move visits somebody has made.
        """
        return await self.interventions.future_period_for_hca(
            hca_id, datetime.now(UTC).date()
        )

    async def future_period_for_customer(
        self, customer_id: str
    ) -> Optional[Tuple[date, date]]:
        """Return the span of a customer's remaining visits, from today.

        Args:
            customer_id (str): The customer whose visits are being measured.

        Returns:
            Optional[Tuple[date, date]]: The first and last day they are
            visited on from today onward, or ``None`` when nothing is planned.
        """
        return await self.interventions.future_period_for_customer(
            customer_id, datetime.now(UTC).date()
        )

    async def queue_replan(
        self,
        requested_by: str,
        company_id: str,
        period: Tuple[date, date],
        publisher: EventPublisher,
        reason: str,
    ) -> PlanningRun:
        """Record a replan and hand it to a worker.

        Args:
            requested_by (str): Who caused it.
            company_id (str): The agency whose queue it belongs on.
            period (Tuple[date, date]): First and last day to replan,
                inclusive.
            publisher (EventPublisher): Queues the solve.
            reason (str): What made the replan necessary, for the log.

        Returns:
            PlanningRun: The pending run, carrying the identifier to poll.

        Notes:
            - **Recorded before it is queued.** A caller handed a 202 must get
              back an identifier that is already real; a run published first
              and stored second could be picked up by a worker before the row
              it names exists.
            - A broker that will not take the message is an ``ERROR`` and not a
              failure: the run stays ``pending`` and the next worker to reach a
              reachable broker will find it. Raising instead would undo a
              deletion that has already happened for a reason unrelated to it.
            - This is the same shape
              :func:`~api.v1.planning.interventions.delete_intervention` has
              used since visits became cancellable, lifted here so the three
              deletions that now end in a replan cannot drift apart.
        """
        period_start, period_end = period
        self.logger.info(
            "Replanning %s to %s because %s.", period_start, period_end, reason
        )
        run = await self.request_run(
            requested_by=requested_by,
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
        )
        queued = await publisher.publish(
            EventRoutingKey.PLANNING_RUN_REQUESTED,
            company_id,
            {"run_id": run.id, "company_id": company_id},
        )
        if not queued:
            self.logger.error(
                "Replan %s is recorded but could not be queued; it stays "
                "pending until the broker is reachable.",
                run.id,
            )
        return run

    async def request_run(
        self,
        requested_by: str,
        company_id: str,
        period_start: date,
        period_end: date,
    ) -> PlanningRun:
        """Record a planning request, before any work is done.

        Args:
            requested_by (str): The administrator asking for it.
            company_id (str): The agency whose calendar the run rewrites.
            period_start (date): First day to plan, inclusive.
            period_end (date): Last day to plan, inclusive.

        Returns:
            PlanningRun: The pending run, carrying the identifier to poll.

        Notes:
            - Separate from :meth:`execute_run` so the endpoint can answer 202
              immediately with something to poll, rather than holding the request
              open for the length of the solve.
            - The agency is recorded on the run rather than resolved from
              ``requested_by`` when the worker picks it up. The account is allowed
              to be gone by then — it carries no foreign key precisely so an
              administrator can leave — and a run that could not name its own
              agency would be a run nothing could safely execute.
        """
        self.logger.info(
            "Planning requested for agency %s from %s to %s by %s.",
            company_id,
            period_start,
            period_end,
            requested_by,
        )
        return await self.runs.create(
            PlanningRun(
                status=PlanningRunStatus.PENDING,
                company_id=company_id,
                requested_by=requested_by,
                period_start=period_start,
                period_end=period_end,
            )
        )

    async def execute_run(self, run_id: str) -> PlanningRun:
        """Solve a pending run and store its plan.

        Args:
            run_id (str): The run to execute.

        Returns:
            PlanningRun: The finished run, succeeded or failed.

        Raises:
            MTPlanningRunNotFound: If no such run exists.

        Notes:
            - Never raises for a solver problem. A failure is recorded on the run
              with its message, because the caller polling for a result needs to
              be told what went wrong — an exception disappearing into a
              background task would leave the run pending for ever.
            - **A run this worker could not claim is returned untouched.** It is
              not an error and not a failure: another worker holds it, or it has
              already finished, and in both cases the right thing to do is
              nothing. Returning it rather than raising is what lets the handler
              acknowledge the message instead of dead-lettering a run that is
              being solved correctly somewhere else.
        """
        run = await self._get_run(run_id)
        claimed = await self._claim(run)
        if claimed is None:
            return run
        run = claimed
        # Measured from the claim, not from the message arriving: what is being
        # asked is how long this worker took, and time spent queued behind
        # another run is the queue's figure rather than the solver's.
        started = monotonic()
        try:
            solution, requirements, assistants = await self._solve(run)
            scheduled = await self._store(run, solution, requirements, assistants)
        except Exception as exc:  # noqa: BLE001 - recorded on the run
            self.logger.error("Planning run %s failed: %s", run_id, exc)
            self._record_outcome(PlanningRunStatus.FAILED, monotonic() - started)
            return await self._finish(
                run,
                status=PlanningRunStatus.FAILED,
                error_message=str(exc),
            )
        self._record_outcome(
            PlanningRunStatus.SUCCEEDED, monotonic() - started, scheduled
        )
        return await self._finish(
            run,
            status=PlanningRunStatus.SUCCEEDED,
            travel_minutes=solution.total_travel_minutes,
            scheduled_count=scheduled,
            unassigned=solution.unassigned_requirement_ids,
        )

    async def get_run(self, run_id: str) -> PlanningRun:
        """Return a run by identifier.

        Args:
            run_id (str): The run to read.

        Returns:
            PlanningRun: The run.

        Raises:
            MTPlanningRunNotFound: If no such run exists.
        """
        return await self._get_run(run_id)

    async def list_runs(
        self, page: int = 1, size: Optional[int] = None
    ) -> List[PlanningRun]:
        """Return a page of runs, most recent period first.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[PlanningRun]: The runs.
        """
        return await self.runs.list(page=page, size=size)

    async def planning_for(
        self, hca_id: str, caller: User, period_start: date, period_end: date
    ) -> HcaPlanning:
        """Return one assistant's diary, if the caller may see it.

        Args:
            hca_id (str): The assistant whose diary is wanted.
            caller (User): Who is asking.
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            HcaPlanning: The diary.

        Raises:
            MTPlanningForbidden: If an assistant asks for somebody else's.

        Notes:
            **This is the row-level check.** A route guard proves only that the
            caller is *an* assistant; it cannot stop assistant A passing
            assistant B's identifier. Managers and administrators pass through
            — they are meant to see every diary.
        """
        if not caller.owns_hca(hca_id):
            self.logger.warning(
                "Assistant %s tried to read the diary of assistant %s.",
                caller.hca_id,
                hca_id,
            )
            raise MTPlanningForbidden("You may only view your own planning.")
        assistant = await self.hcas.get(hca_id)
        if assistant is None:
            self.logger.warning("Diary requested for absent assistant %s.", hca_id)
            raise MTPlanningRunNotFound(f"No assistant {hca_id!r} exists.")
        visits = await self.interventions.list_for_hca(hca_id, period_start, period_end)
        self.logger.info(
            "Serving %d visit(s) for assistant %s from %s to %s.",
            len(visits),
            hca_id,
            period_start,
            period_end,
        )
        return HcaPlanning(
            hca_id=hca_id,
            hca_full_name=assistant.full_name(),
            period_start=period_start,
            period_end=period_end,
            interventions=visits,
        )

    async def all_plannings(
        self, caller: User, period_start: date, period_end: date
    ) -> List[HcaPlanning]:
        """Return every assistant's diary over a period.

        Args:
            caller (User): Who is asking.
            period_start (date): First day of interest, inclusive.
            period_end (date): Last day of interest, inclusive.

        Returns:
            List[HcaPlanning]: One diary per assistant with work.

        Raises:
            MTPlanningForbidden: If an assistant asks for the whole workforce.

        Notes:
            An assistant calling this gets their own diary back, not an error
            — the screen is the same one, and refusing it would be gratuitous.
            What they must never get is anybody else's, which the per-assistant
            check below still enforces.
        """
        if not caller.is_manager():
            if caller.hca_id is None:
                self.logger.warning(
                    "Account %s asked for every planning but is bound to no "
                    "assistant record.",
                    caller.email,
                )
                raise MTPlanningForbidden("You may only view your own planning.")
            self.logger.debug(
                "Assistant %s asked for every planning; serving only their own.",
                caller.hca_id,
            )
            return [
                await self.planning_for(caller.hca_id, caller, period_start, period_end)
            ]
        hca_ids = await self.interventions.list_hca_ids_for_period(
            period_start, period_end
        )
        self.logger.info(
            "Serving %d planning(s) for %s to %s.",
            len(hca_ids),
            period_start,
            period_end,
        )
        plannings: List[HcaPlanning] = []
        for hca_id in hca_ids:
            plannings.append(
                await self.planning_for(hca_id, caller, period_start, period_end)
            )
        return plannings

    def build(
        self,
        quotes: List[Quote],
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
        period_start: date,
        period_end: date,
    ) -> List[InterventionRequirement]:
        """Return the work to schedule for a period.

        Args:
            quotes (List[Quote]): The accepted quotes covering the period.
            customers (Dict[str, Customer]): The customers those quotes are
                for, keyed by identifier.
            catalog (Dict[str, InterventionType]): The services those quotes
                sell, keyed by identifier, read for the qualifications each
                requires.
            period_start (date): First day to plan, inclusive.
            period_end (date): Last day to plan, inclusive.

        Returns:
            List[InterventionRequirement]: The schedulable work.

        Notes:
            - A quote that is not accepted contributes nothing, even if it was
              passed in. The repository already filters on status; checking
              again here means the rule holds however this is called.
            - **The certification requirement is resolved here, once.** A line
              may override its catalog entry — see
              :meth:`~models.quoting.quote_line.QuoteLine.effective_certification_codes`
              — and doing that here means the solver never needs the catalog,
              never holds a second lookup table, and never has to know the
              inheritance rule exists.
            - A line whose catalog entry has vanished falls back to requiring
              **nothing**, at ``WARNING``, for both kinds of requirement. The
              alternatives are both worse: an exception would fail the whole run
              over one missing row, and inventing a requirement would strand
              work nobody could be qualified for. The line is still planned, and
              the log names it.
            - The skill requirement is resolved here too, and by the same rule —
              see
              :meth:`~models.quoting.quote_line.QuoteLine.effective_skill_codes`.
              Resolving both in one place is what keeps the solver from needing
              the catalog at all.
        """
        self.logger.info(
            "Building requirements from %d quote(s) for %s to %s.",
            len(quotes),
            period_start,
            period_end,
        )
        requirements: List[InterventionRequirement] = []
        skipped_unroutable = 0
        skipped_out_of_period = 0
        skipped_interrupted = 0

        for quote in quotes:
            if not quote.is_schedulable():
                self.logger.warning(
                    "Quote %s is %s and not priced for scheduling; skipping it.",
                    quote.reference,
                    quote.status.value,
                )
                continue
            customer = customers.get(quote.customer_id)
            location = customer.address.to_geo_point() if customer is not None else None
            for line in quote.lines:
                if not period_start <= line.service_date <= period_end:
                    skipped_out_of_period += 1
                    continue
                if not quote.covers(line.service_date):
                    skipped_interrupted += 1
                    continue
                if location is None:
                    skipped_unroutable += 1
                    self.logger.warning(
                        "Quote %s line %r cannot be planned: customer %s has no "
                        "resolved address (%s).",
                        quote.reference,
                        line.name,
                        quote.customer_id,
                        customer.address.geocoding_error if customer else "unknown",
                    )
                    continue
                entry = catalog.get(line.intervention_type_id)
                if entry is None:
                    self.logger.warning(
                        "Quote %s line %r names catalog entry %s, which is not "
                        "loaded; it is planned as requiring no qualification.",
                        quote.reference,
                        line.name,
                        line.intervention_type_id,
                    )
                codes = line.effective_certification_codes(
                    entry.required_certification_codes if entry else []
                )
                skill_codes = line.effective_skill_codes(
                    entry.required_skill_codes if entry else []
                )
                requirements.append(
                    InterventionRequirement(
                        id=line.id if line.id else f"{quote.id}:{line.name}",
                        quote_line_id=line.id if line.id else "",
                        customer_id=quote.customer_id,
                        name=line.name,
                        intervention_type_id=line.intervention_type_id,
                        day=line.service_date,
                        window_start_minute=self._to_minutes(line.earliest_start),
                        window_end_minute=self._to_minutes(line.latest_end),
                        duration_minutes=line.duration_minutes,
                        location=location,
                        required_certification_codes=codes,
                        required_skill_codes=skill_codes,
                    )
                )

        self.logger.info(
            "Built %d requirement(s); skipped %d outside the period, %d past an "
            "interruption and %d unroutable.",
            len(requirements),
            skipped_out_of_period,
            skipped_interrupted,
            skipped_unroutable,
        )
        if skipped_unroutable:
            self.logger.error(
                "%d piece(s) of accepted work cannot be planned at all until "
                "their customer's address resolves.",
                skipped_unroutable,
            )
        if not requirements:
            self.logger.warning(
                "No schedulable work between %s and %s.",
                period_start,
                period_end,
            )
        return requirements

    def travel_index_for(self, hca_id: str, point: GeoPoint) -> int:
        """Return the index a place has in one assistant's travel table.

        Args:
            hca_id (str): The assistant whose table to read.
            point (GeoPoint): The place to look up.

        Returns:
            int: Its index.

        Raises:
            KeyError: If the assistant has no table, or the place was not among
                those it was built over.
        """
        return self.travel_indexes[hca_id][(point.latitude, point.longitude)]

    def travel_between(
        self, hca_id: str, origin_index: int, destination_index: int
    ) -> int:
        """Return one assistant's travel time between two indexed places.

        Args:
            hca_id (str): The assistant making the journey.
            origin_index (int): Where it starts.
            destination_index (int): Where it ends.

        Returns:
            int: The travel time in minutes.
        """
        return self.travel_minutes[hca_id][(origin_index, destination_index)]

    def travel_between_points(
        self, hca_id: str, origin: GeoPoint, destination: GeoPoint
    ) -> int:
        """Return one assistant's travel time between two places.

        Args:
            hca_id (str): The assistant making the journey.
            origin (GeoPoint): Where the journey starts.
            destination (GeoPoint): Where it ends.

        Returns:
            int: The travel time in minutes.

        Raises:
            KeyError: If either place is outside that assistant's table.

        Notes:
            Keyed by assistant because the table is per assistant: a licensed
            one covers ground far faster than one on public transport, and a
            single shared table would have to assume one speed for everybody.
        """
        return self.travel_between(
            hca_id,
            self.travel_index_for(hca_id, origin),
            self.travel_index_for(hca_id, destination),
        )

    def solve(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],
        settings: PlanningSettings,
    ) -> PlanningSolution:
        """Build and solve the planning problem.

        Args:
            requirements (List[InterventionRequirement]): The accepted work.
            assistants (List[Hca]): The workforce available.
            settings (PlanningSettings): The manager-owned rules: the
                intervention radius and the lunch-break length.

        Returns:
            PlanningSolution: The best plan found, with whatever could not be
            placed listed explicitly.

        Notes:
            Returns rather than raises on an empty input. A week with no
            accepted work is a legitimate answer, not an error.
        """
        if not requirements:
            self.logger.warning("Nothing to plan: no requirement was supplied.")
            return PlanningSolution(is_feasible=True, status_name="EMPTY")
        if not assistants:
            self.logger.warning(
                "Nobody to plan for: %d requirement(s) cannot be assigned.",
                len(requirements),
            )
            return PlanningSolution(
                unassigned_requirement_ids=[item.id for item in requirements],
                is_feasible=True,
                status_name="NO_ASSISTANTS",
            )

        self.logger.info(
            "Planning %d requirement(s) across %d assistant(s).",
            len(requirements),
            len(assistants),
        )
        self._reset()
        self.settings = settings
        self._build_assignment_vars(requirements, assistants)
        self._build_interval_vars(requirements, assistants)
        self._add_day_bounds(requirements)
        self._add_availability(requirements, assistants)
        self._add_certifications(requirements, assistants)
        self._add_skills(requirements, assistants)
        self._add_radius(requirements, assistants)
        self._add_customer_conflicts(requirements)
        for assistant in assistants:
            for day, day_requirements in self._by_day(requirements).items():
                self._add_no_overlap(assistant, day, day_requirements)
                self._add_lunch_break(assistant, day, day_requirements)
                self._add_travel(assistant, day, day_requirements)
        self._add_objective(requirements)
        return self._run(requirements)
