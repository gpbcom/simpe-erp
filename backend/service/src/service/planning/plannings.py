from __future__ import annotations

# Standard library imports
import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, time
from logging import Logger, getLogger
import math
from typing import Dict, List, Optional, Tuple

# Third-party imports
from ortools.sat.python import cp_model

# First-party imports
from models.auth.user import User
from models.configuration.planning_config import PlanningConfig
from models.enums import PlanningRunStatus, UnplacedReason
from models.geo.geo_point import GeoPoint
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.people.hca import Hca
from models.planning.hca_planning import HcaPlanning
from models.planning.intervention import Intervention
from models.planning.intervention_requirement import InterventionRequirement
from models.planning.planning_run import PlanningRun
from models.planning.planning_solution import (
    PlanningSolution,
    ScheduledAssignment,
)
from models.planning.unplaced_requirement import UnplacedRequirement
from models.quoting.quote import Quote
from models.settings.planning_settings import PlanningSettings
from service.planning.exceptions import (
    MTPlanningForbidden,
    MTPlanningInconsistentSolution,
    MTPlanningInfeasible,
    MTPlanningInvalidSpeed,
    MTPlanningRunNotFound,
    MTPlanningSettingsUnavailable,
)
from storage.repositories.customer import CustomerRepository
from storage.repositories.hca import HcaRepository
from storage.repositories.intervention import InterventionRepository
from storage.repositories.planning_run import PlanningRunRepository
from storage.repositories.planning_settings import PlanningSettingsRepository
from storage.repositories.quote import QuoteRepository


class PlanningService:
    """Owns the planning: its rules, its computation, and the diaries it makes.

    Attributes:
        runs (PlanningRunRepository): The run records.
        interventions (InterventionRepository): The scheduled visits.
        quotes (QuoteRepository): The accepted work.
        customers (CustomerRepository): Where the work happens.
        hcas (HcaRepository): The workforce.
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
        settings: PlanningSettingsRepository,
        config: PlanningConfig,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            runs (PlanningRunRepository): The run records.
            interventions (InterventionRepository): The scheduled visits.
            quotes (QuoteRepository): The accepted work.
            customers (CustomerRepository): Where the work happens.
            hcas (HcaRepository): The workforce.
            builder (RequirementBuilder): Builds the schedulable work.
            settings (PlanningSettingsRepository): The manager-owned rules.
            config (PlanningConfig): Planning parameters.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.runs = runs
        self.interventions = interventions
        self.quotes = quotes
        self.customers = customers
        self.hcas = hcas
        self.settings = settings
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        # Per-solve state, keyed by assistant. Empty until build_travel runs,
        # which every solve does first. A service instance is built per request
        # and serves one run, so there is no second solve to collide with.
        self.travel_points: Dict[str, List[GeoPoint]] = {}
        self.travel_indexes: Dict[str, Dict[Tuple[float, float], int]] = {}
        self.travel_minutes: Dict[str, Dict[Tuple[int, int], int]] = {}
        self.logger.debug("PlanningService created.")

    ############################
    # Internal Helpers Methods #
    ############################

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

    async def _mark_running(self, run: PlanningRun) -> PlanningRun:
        """Record that the solver has started.

        Args:
            run (PlanningRun): The run being executed.

        Returns:
            PlanningRun: The updated run.
        """
        self.logger.debug("Marking planning run %s as running.", run.id)
        updated = await self.runs.update(
            run.model_copy(
                update={
                    "status": PlanningRunStatus.RUNNING,
                    "started_at": datetime.now(UTC),
                }
            )
        )
        if updated is None:
            self.logger.warning(
                "Could not mark planning run %s as running; it will keep "
                "reporting as pending while the solver works.",
                run.id,
            )
            return run
        self.logger.info("Planning run %s is running.", run.id)
        return updated

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
        quotes = await self.quotes.list_schedulable(run.period_start, run.period_end)  # noqa: E501
        customers: Dict[str, Customer] = {}
        for quote in quotes:
            if quote.customer_id not in customers:
                customer = await self.customers.get(quote.customer_id)
                if customer is not None:
                    customers[quote.customer_id] = customer
        requirements = self.build(quotes, customers, run.period_start, run.period_end)
        assistants = await self.hcas.list_all()
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
            **A partial plan is refused, not stored.** A calendar missing three
            visits still looks like a calendar; nobody reads the run record to
            check, and the visits quietly dropped are the ones that end with a
            customer waiting at the door. Failing means this week's existing
            plan stays untouched — :meth:`_store` is never reached — so the
            agency keeps a working calendar while the problem is fixed.

            The message names each visit and why it did not fit, so a manager
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
                # Silently skipping would leave the assistant idle all week
                # with nothing anywhere saying why.
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
                # A zero or negative speed makes every journey infinite. Caught
                # here rather than surfacing as a division error deep inside
                # the table build, where the assistant it belongs to is lost.
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
            run.period_start, run.period_end, visits
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
                # The visit cannot be written without somewhere to send the
                # assistant, and the caller sees only the resulting failure —
                # so the missing customer has to be named here.
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
                "No assistant has a resolved home; distance cannot be measured."
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
            Each check answers a question the solver's model folds together, so
            the first one that applies is reported and the rest are not tested.
            A visit nobody can reach is also a visit with no feasible slot, but
            only the first reading tells anybody what to change.
        """
        if (
            requirement.window_start_minute < self.config.day_start_minute
            or requirement.window_end_minute > self.config.day_end_minute
        ):
            return UnplacedRequirement(
                requirement_id=requirement.id,
                name=requirement.name,
                customer_id=requirement.customer_id,
                day=requirement.day,
                reason=UnplacedReason.OUTSIDE_WORKING_DAY,
                detail=(
                    f"its window falls outside the "
                    f"{self.config.day_start_minute // 60:02d}:00–"
                    f"{self.config.day_end_minute // 60:02d}:00 working day"
                ),
            )

        reachable = self._reachable_assistants(requirement, assistants, settings)
        if not reachable:
            nearest = self._nearest_home_km(requirement, assistants)
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

        if not [
            assistant
            for assistant in reachable
            if assistant.is_available_on(requirement.day)
        ]:
            return UnplacedRequirement(
                requirement_id=requirement.id,
                name=requirement.name,
                customer_id=requirement.customer_id,
                day=requirement.day,
                reason=UnplacedReason.NO_ASSISTANT_AVAILABLE,
                detail=(
                    f"all {len(reachable)} assistant(s) within the radius are "
                    f"absent on {requirement.day}"
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
        assistants: List[Hca],  # noqa: E501
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
        assistants: List[Hca],  # noqa: E501
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

    def _add_day_bounds(self, requirements: List[InterventionRequirement]) -> None:  # noqa: E501
        """Keep every visit inside the working day.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Notes:
            The window on a requirement comes from the customer; this is the
            agency's own rule — nothing before 09:00, nothing after 20:00 —
            and it applies on top.
        """
        for requirement in requirements:
            self.model.add(self.starts[requirement.id] >= self.config.day_start_minute)  # noqa: E501
            self.model.add(self.ends[requirement.id] <= self.config.day_end_minute)  # noqa: E501

    def _add_availability(
        self,
        requirements: List[InterventionRequirement],
        assistants: List[Hca],  # noqa: E501
    ) -> None:
        """Refuse work to an assistant who is away.

        Args:
            requirements (List[InterventionRequirement]): The work.
            assistants (List[Hca]): The workforce.

        Notes:
            - A whole-day absence forbids the assignment outright. A partial one
              — a morning of training — is handled as a blocking interval in
              :meth:`_add_no_overlap` instead, so the rest of the day stays
              usable.
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
            for requirement in requirements:
                if not assistant.is_available_on(requirement.day):
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
            - Its length comes from the stored settings, not the configuration
              file: the business requires it to be configurable, and a manager
              changing it must not need a deployment.
        """
        works_today = self.model.new_bool_var(f"works_{assistant.id}_{day}")
        assignment_literals = [
            self.assigned[(requirement.id, assistant.id)]
            for requirement in requirements
        ]
        self.model.add_max_equality(works_today, assignment_literals)

        break_start = self.model.new_int_var(
            self.config.lunch_window_start_minute,
            self.config.lunch_window_end_minute - self.settings.lunch_break_minutes,
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
            self.starts[requirement.id] >= self.config.day_start_minute + outbound
        ).only_enforce_if(is_first)

    def _add_objective(self, requirements: List[InterventionRequirement]) -> None:  # noqa: E501
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
        travel_cost = [self.config.travel_weight * term for term in self.travel_terms]  # noqa: E501
        self.model.minimize(sum(dropped_cost) + sum(travel_cost))

    def _run(self, requirements: List[InterventionRequirement]) -> PlanningSolution:  # noqa: E501
        """Search for a solution and read it back.

        Args:
            requirements (List[InterventionRequirement]): The work.

        Returns:
            PlanningSolution: What was found.

        Notes:
            The time limit is what makes this bounded work rather than an open
            question. An optimal answer is preferred, but a good feasible one
            inside the budget is what a planning screen actually needs.
        """
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.solver_time_limit_seconds  # noqa: E501
        solver.parameters.num_search_workers = 8
        self.logger.info(
            "Solving with a %.1fs budget.",
            self.config.solver_time_limit_seconds,  # noqa: E501
        )
        status = solver.solve(self.model)
        status_name = solver.status_name(status)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            self.logger.error(
                "The solver found no plan at all (%s); the constraints are "
                "contradictory rather than merely tight.",
                status_name,
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
                "Planning settings in force: radius %.1f km, lunch %d min.",
                stored.max_intervention_radius_km,
                stored.lunch_break_minutes,
            )
            return stored

        self.logger.info("No planning settings stored; seeding from configuration.")
        seeded = await self.settings.seed(
            PlanningSettings(
                max_intervention_radius_km=self.config.max_intervention_radius_km,
                lunch_break_minutes=self.config.lunch_break_minutes,
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
    ) -> PlanningSettings:
        """Change the rules.

        Args:
            max_intervention_radius_km (float): The new radius, in kilometres.
            lunch_break_minutes (int): The new break length, in minutes.
            updated_by (str): The account making the change.

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
                lunch_break_minutes=lunch_break_minutes,
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
            "Planning settings changed by %s: radius %.1f km, lunch %d min. "
            "They apply to the next planning run, not to plans already made.",
            updated_by,
            updated.max_intervention_radius_km,
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

    async def request_run(
        self, requested_by: str, period_start: date, period_end: date
    ) -> PlanningRun:
        """Record a planning request, before any work is done.

        Args:
            requested_by (str): The administrator asking for it.
            period_start (date): First day to plan, inclusive.
            period_end (date): Last day to plan, inclusive.

        Returns:
            PlanningRun: The pending run, carrying the identifier to poll.

        Notes:
            Separate from :meth:`execute_run` so the endpoint can answer 202
            immediately with something to poll, rather than holding the request
            open for the length of the solve.
        """
        self.logger.info(
            "Planning requested for %s to %s by %s.",
            period_start,
            period_end,
            requested_by,
        )
        return await self.runs.create(
            PlanningRun(
                status=PlanningRunStatus.PENDING,
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
            Never raises for a solver problem. A failure is recorded on the run
            with its message, because the caller polling for a result needs to
            be told what went wrong — an exception disappearing into a
            background task would leave the run pending for ever.
        """
        run = await self._get_run(run_id)
        run = await self._mark_running(run)
        try:
            solution, requirements, assistants = await self._solve(run)
            scheduled = await self._store(run, solution, requirements, assistants)
        except Exception as exc:  # noqa: BLE001 - recorded on the run
            self.logger.error("Planning run %s failed: %s", run_id, exc)
            return await self._finish(
                run,
                status=PlanningRunStatus.FAILED,
                error_message=str(exc),
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
        period_start: date,
        period_end: date,
    ) -> List[InterventionRequirement]:
        """Return the work to schedule for a period.

        Args:
            quotes (List[Quote]): The accepted quotes covering the period.
            customers (Dict[str, Customer]): The customers those quotes are
                for, keyed by identifier.
            period_start (date): First day to plan, inclusive.
            period_end (date): Last day to plan, inclusive.

        Returns:
            List[InterventionRequirement]: The schedulable work.

        Notes:
            A quote that is not accepted contributes nothing, even if it was
            passed in. The repository already filters on status; checking again
            here means the rule holds however this is called.
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
                # An interrupted arrangement stops producing work the day after
                # its last one. Filtered here rather than at the repository,
                # because the interruption cuts a quote in half: the days before
                # it are still planned, and a query that dropped the whole quote
                # would cancel visits the family is expecting this week.
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
                "No schedulable work between %s and %s.", period_start, period_end
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
        self._add_radius(requirements, assistants)
        self._add_customer_conflicts(requirements)
        for assistant in assistants:
            for day, day_requirements in self._by_day(requirements).items():
                self._add_no_overlap(assistant, day, day_requirements)
                self._add_lunch_break(assistant, day, day_requirements)
                self._add_travel(assistant, day, day_requirements)
        self._add_objective(requirements)
        return self._run(requirements)
