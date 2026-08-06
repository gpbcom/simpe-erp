from __future__ import annotations

# Standard library imports
from decimal import Decimal
from enum import StrEnum, unique
from typing import Tuple

# First-party imports
from models.exceptions.enum_exceptions import (
    MTInvalidWeekday,
    MTRoutingKeyMissingCompany,
)


@unique
class RegistrationStatus(StrEnum):
    """Enumeration for the registration status of a customer.

    Attributes:
        ACTIVE (str): The customer is registered and may be quoted and served.
        STOPPED (str): The customer has stopped the service; no new quote or
            intervention may be created for them.
    """

    ACTIVE = "active"
    STOPPED = "stopped"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every registration-status value.

        Returns:
            Tuple[str, ...]: ``("active", "stopped")``.
        """
        return tuple(status.value for status in cls)


@unique
class ContractType(StrEnum):
    """Enumeration for the employment contract of a Home Care Assistant.

    Attributes:
        CDI (str): Permanent open-ended contract (contrat à durée indéterminée).
        CDD (str): Fixed-term contract (contrat à durée déterminée).
        INTERIM (str): Temporary agency contract.
        INTERNSHIP (str): Internship (stage).
    """

    CDI = "cdi"
    CDD = "cdd"
    INTERIM = "interim"
    INTERNSHIP = "internship"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every contract-type value.

        Returns:
            Tuple[str, ...]: The four supported contract types.
        """
        return tuple(contract.value for contract in cls)


@unique
class ServiceCategory(StrEnum):
    """Enumeration for the VAT category an intervention type falls under.

    Attributes:
        NECESSITY (str): Service delivered for a necessity reason, taxed at the
            reduced 5.5% VAT rate.
        COMFORT (str): Service delivered for a comfort reason, taxed at the
            standard 20% VAT rate.

    Notes:
        The category is carried by the intervention type rather than by the
        quote line: a given type of care is structurally one or the other. A
        type that would need both categories must be split into two types.
    """

    NECESSITY = "necessity"
    COMFORT = "comfort"

    def vat_rate(self) -> Decimal:
        """Return the VAT rate applicable to this category.

        Returns:
            Decimal: ``Decimal("0.055")`` for a necessity service, and
            ``Decimal("0.20")`` for a comfort service.

        Notes:
            The rate is a :class:`~decimal.Decimal` and never a float, so it
            composes with the rest of the pricing arithmetic without losing
            cents to binary floating-point representation.
        """
        rates = {
            ServiceCategory.NECESSITY: Decimal("0.055"),
            ServiceCategory.COMFORT: Decimal("0.20"),
        }
        return rates[self]

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every service-category value.

        Returns:
            Tuple[str, ...]: ``("necessity", "comfort")``.
        """
        return tuple(category.value for category in cls)


@unique
class UserRole(StrEnum):
    """Enumeration for the role granted to an authenticated account.

    Attributes:
        HCA (str): A Home Care Assistant. Declares their own availability and
            sees their own planning only.
        MANAGER (str): Sees every HCA planning, manages customers, quotes and
            the intervention-type catalog, and edits an HCA's contract type
            and certifications.
        ADMIN (str): Everything a manager can do, plus running the planning
            computation and promoting a user to manager.
    """

    HCA = "hca"
    MANAGER = "manager"
    ADMIN = "admin"

    def rank(self) -> int:
        """Return the numeric access rank of this role.

        Returns:
            int: The access rank; a higher rank unlocks strictly more.

        Notes:
            The ordering is shared by the whole stack so the API guards and any
            client agree on which role unlocks which feature. Rank comparison
            answers "at least a manager"; it must not be used for the checks
            that are specific to being an HCA (such as owning a planning),
            which compare the role by identity instead.
        """
        ranks = {UserRole.HCA: 0, UserRole.MANAGER: 1, UserRole.ADMIN: 2}
        return ranks[self]

    def has_at_least(self, minimum: UserRole) -> bool:
        """Return whether this role ranks at or above ``minimum``.

        Args:
            minimum (UserRole): The lowest role that satisfies the check.

        Returns:
            bool: ``True`` when this role's rank is greater than or equal to
            the rank of ``minimum``.
        """
        return self.rank() >= minimum.rank()

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every role value.

        Returns:
            Tuple[str, ...]: ``("hca", "manager", "admin")``.
        """
        return tuple(role.value for role in cls)


@unique
class QuoteStatus(StrEnum):
    """Enumeration for the lifecycle status of a quote.

    Attributes:
        DRAFT (str): Being composed; lines may still be added or removed.
        PENDING_VALIDATION (str): Submitted by an assistant and waiting for a
            manager to validate it.
        SENT (str): Sent to the customer and awaiting their answer.
        ACCEPTED (str): Accepted by the customer. Only accepted quotes feed the
            planning computation.
        REJECTED (str): Declined by the customer.
        EXPIRED (str): Its validity date passed before an answer was given.

    Notes:
        ``PENDING_VALIDATION`` sits between the draft and the customer. An
        assistant knows what a customer needs but does not set the agency's
        prices, so a quote they write waits for a manager before it can be sent.
        It is deliberately a status rather than a flag: a quote is in exactly
        one place at a time, and a boolean beside the status would allow the
        nonsense of an accepted quote still awaiting validation.
    """

    DRAFT = "draft"
    PENDING_VALIDATION = "pending-validation"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every quote-status value.

        Returns:
            Tuple[str, ...]: The six supported statuses.
        """
        return tuple(status.value for status in cls)

    def is_editable(self) -> bool:
        """Return whether the lines may still be changed.

        Returns:
            bool: ``True`` only for a draft.

        Notes:
            A quote awaiting validation is frozen: a manager must decide on the
            figures they were shown, not on figures that moved underneath them
            while they read.
        """
        return self is QuoteStatus.DRAFT

    def is_awaiting_validation(self) -> bool:
        """Return whether a manager still owes this quote a decision.

        Returns:
            bool: ``True`` when the quote sits in the validation queue.
        """
        return self is QuoteStatus.PENDING_VALIDATION


@unique
class InterventionStatus(StrEnum):
    """Enumeration for the lifecycle status of a scheduled intervention.

    Attributes:
        PLANNED (str): Produced by the planning computation, not yet confirmed.
        CONFIRMED (str): Acknowledged by the assigned Home Care Assistant.
        COMPLETED (str): Delivered.
        CANCELLED (str): Called off; it no longer occupies the HCA's day.
    """

    PLANNED = "planned"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every intervention-status value.

        Returns:
            Tuple[str, ...]: The four supported statuses.
        """
        return tuple(status.value for status in cls)


@unique
class AvailabilityKind(StrEnum):
    """Enumeration for the reason a Home Care Assistant is unavailable.

    Attributes:
        HOLIDAY (str): Paid annual leave.
        DAY_OFF (str): A non-working day in the HCA's week.
        SICK_LEAVE (str): Medical leave.
        TRAINING (str): Attending a training session.
        UNAVAILABLE (str): Unavailable for any other reason.

    Notes:
        Every kind blocks scheduling identically; the distinction is recorded
        for reporting, not for the solver, which only asks whether a slot
        exists for a given day.
    """

    HOLIDAY = "holiday"
    DAY_OFF = "day-off"
    SICK_LEAVE = "sick-leave"
    TRAINING = "training"
    UNAVAILABLE = "unavailable"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every availability-kind value.

        Returns:
            Tuple[str, ...]: The five supported kinds.
        """
        return tuple(kind.value for kind in cls)


@unique
class Weekday(StrEnum):
    """Enumeration for the days of the week.

    Attributes:
        MONDAY (str): Monday, ISO weekday 1.
        TUESDAY (str): Tuesday, ISO weekday 2.
        WEDNESDAY (str): Wednesday, ISO weekday 3.
        THURSDAY (str): Thursday, ISO weekday 4.
        FRIDAY (str): Friday, ISO weekday 5.
        SATURDAY (str): Saturday, ISO weekday 6.
        SUNDAY (str): Sunday, ISO weekday 7.
    """

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    def iso_weekday(self) -> int:
        """Return the ISO weekday number of this day.

        Returns:
            int: ``1`` for Monday through ``7`` for Sunday, matching
            :meth:`datetime.date.isoweekday`.
        """
        numbers = {
            Weekday.MONDAY: 1,
            Weekday.TUESDAY: 2,
            Weekday.WEDNESDAY: 3,
            Weekday.THURSDAY: 4,
            Weekday.FRIDAY: 5,
            Weekday.SATURDAY: 6,
            Weekday.SUNDAY: 7,
        }
        return numbers[self]

    @classmethod
    def from_iso_weekday(cls, iso_weekday: int) -> Weekday:
        """Return the weekday matching an ISO weekday number.

        Args:
            iso_weekday (int): The ISO weekday number, ``1`` (Monday) to ``7``
                (Sunday), as returned by :meth:`datetime.date.isoweekday`.

        Returns:
            Weekday: The matching weekday.

        Raises:
            MTInvalidWeekday: If ``iso_weekday`` is outside the ``1..7`` range.
        """
        members = tuple(cls)
        if not isinstance(iso_weekday, int) or not 1 <= iso_weekday <= len(members):  # noqa: E501
            raise MTInvalidWeekday(
                f"Invalid ISO weekday: {iso_weekday!r}. Must be an int in 1..7."
            )
        return members[iso_weekday - 1]  # noqa: E501

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every weekday value.

        Returns:
            Tuple[str, ...]: The seven weekday values, Monday first.
        """
        return tuple(day.value for day in cls)


@unique
class PlanningRunStatus(StrEnum):
    """Enumeration for the lifecycle status of a planning computation.

    Attributes:
        PENDING (str): Accepted and queued, not yet picked up.
        RUNNING (str): The solver is running.
        SUCCEEDED (str): The solver finished and the interventions were written.
        FAILED (str): The run ended on an error; see the run's error message.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    def is_terminal(self) -> bool:
        """Return whether no further status change can follow this one.

        Returns:
            bool: ``True`` for :attr:`SUCCEEDED` and :attr:`FAILED`.

        Notes:
            Clients poll a run until this returns ``True``.
        """
        return self in (PlanningRunStatus.SUCCEEDED, PlanningRunStatus.FAILED)

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every planning-run-status value.

        Returns:
            Tuple[str, ...]: The four supported statuses.
        """
        return tuple(status.value for status in cls)


@unique
class ProbeStatus(StrEnum):
    """Enumeration for what an observability probe reports.

    Attributes:
        OK (str): The probe passed.
        UNAVAILABLE (str): The probe failed and the instance should be taken
            out of the load balancer.

    Notes:
        Shared by ``/health`` and ``/ready`` so an orchestrator reads one
        vocabulary from both. ``/health`` only ever reports :attr:`OK` — a
        liveness probe that fails gets the container restarted, and an API
        whose database blinked must not be.
    """

    OK = "ok"
    UNAVAILABLE = "unavailable"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every probe-status value.

        Returns:
            Tuple[str, ...]: ``("ok", "unavailable")``.
        """
        return tuple(status.value for status in cls)


@unique
class DatabaseStatus(StrEnum):
    """Enumeration for whether the database answered a readiness check.

    Attributes:
        REACHABLE (str): The database answered.
        UNREACHABLE (str): The database did not answer, or the check itself
            failed.

    Notes:
        Reported alongside :class:`ProbeStatus` so an operator reading a 503
        can tell "the store is down" from any other reason the instance is not
        ready, without opening the logs.
    """

    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every database-status value.

        Returns:
            Tuple[str, ...]: ``("reachable", "unreachable")``.
        """
        return tuple(status.value for status in cls)


@unique
class UnplacedReason(StrEnum):
    """Why a piece of accepted work could not be scheduled.

    Attributes:
        OUT_OF_RADIUS: No assistant lives within the configured radius of it.
        NO_ASSISTANT_AVAILABLE: Everybody near enough is absent that day.

    Notes on what is *not* here: a window narrower than the service it
    holds has no member, because
    :class:`~models.planning.intervention_requirement.InterventionRequirement`
    refuses to build one. A reason that can never be reported would be a
    branch nothing exercises.
        OUTSIDE_WORKING_DAY: Its window falls outside the working day.
        CUSTOMER_CONFLICT: The customer has overlapping visits that cannot all
            fit without one starting before another ends.
        NO_FEASIBLE_SLOT: It could not be fitted around the rest of the plan —
            travel, lunch and the other visits together leave no room.

    Notes:
        The reasons are ordered from most to least specific, and the checker
        reports the first that applies. "Out of radius" and "no feasible slot"
        are both true of a visit nobody can reach, but only the first tells a
        planner what to change.
    """

    OUT_OF_RADIUS = "out-of-radius"
    NO_ASSISTANT_AVAILABLE = "no-assistant-available"
    OUTSIDE_WORKING_DAY = "outside-working-day"
    CUSTOMER_CONFLICT = "customer-conflict"
    NO_FEASIBLE_SLOT = "no-feasible-slot"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every unplaced-reason value.

        Returns:
            Tuple[str, ...]: The five reasons work can go unplaced.
        """
        return tuple(reason.value for reason in cls)


@unique
class HcaApplicationStatus(StrEnum):
    """Where a self-submitted assistant registration has got to.

    Attributes:
        PENDING: Submitted, waiting for the chosen company to decide.
        APPROVED: Accepted; the assistant record and the account now exist.
        REJECTED: Declined; no account was ever created.

    Notes:
        Terminal states are kept rather than deleted. An applicant who was
        declined and applies again should be recognisable as such, and a
        deleted row cannot be.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every application-status value.

        Returns:
            Tuple[str, ...]: ``("pending", "approved", "rejected")``.
        """
        return tuple(status.value for status in cls)

    def is_terminal(self) -> bool:
        """Return whether the application has been decided.

        Returns:
            bool: ``True`` for approved and rejected.
        """
        return self in (HcaApplicationStatus.APPROVED, HcaApplicationStatus.REJECTED)


@unique
class AccountOrigin(StrEnum):
    """How an account came to exist.

    Attributes:
        SELF_REGISTERED: The assistant applied and a company approved them.
        CREATED_BY_STAFF: An administrator or manager created it and issued a
            temporary password.

    Notes:
        Recorded because the two paths carry different obligations. An account
        created by staff starts with a password its owner has never chosen, and
        must be made to choose one before it can do anything; a self-registered
        account chose its own at the point of applying.
    """

    SELF_REGISTERED = "self-registered"
    CREATED_BY_STAFF = "created-by-staff"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every account-origin value.

        Returns:
            Tuple[str, ...]: ``("self-registered", "created-by-staff")``.
        """
        return tuple(origin.value for origin in cls)


@unique
class NotificationKind(StrEnum):
    """Enumeration for what a notification is about.

    Attributes:
        QUOTE_SUBMITTED (str): An assistant sent a quote for validation.
        QUOTE_VALIDATED (str): A manager approved a submitted quote.
        QUOTE_REFUSED (str): A manager sent a submitted quote back.
        PLANNING_COMPLETED (str): A planning run finished and calendars moved.

    Notes:
        The kind is what a client keys its icon, colour and deep link off, so it
        is an enumeration rather than free text. A notification whose kind
        nothing recognises is one the interface cannot route the reader
        anywhere useful from.
    """

    QUOTE_SUBMITTED = "quote-submitted"
    QUOTE_VALIDATED = "quote-validated"
    QUOTE_REFUSED = "quote-refused"
    PLANNING_COMPLETED = "planning-completed"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every notification-kind value.

        Returns:
            Tuple[str, ...]: The four supported kinds.
        """
        return tuple(kind.value for kind in cls)

    def concerns_a_quote(self) -> bool:
        """Return whether the notification points at a quote.

        Returns:
            bool: ``True`` for the three quote-workflow kinds.

        Notes:
            Used to decide whether ``quote_id`` is expected to be populated,
            which is what makes the notification clickable.
        """
        return self is not NotificationKind.PLANNING_COMPLETED


@unique
class EventRoutingKey(StrEnum):
    """Enumeration for the topics the agency publishes events under.

    Attributes:
        QUOTE_SUBMITTED (str): An assistant sent a quote for validation.
        QUOTE_VALIDATED (str): A manager approved a submitted quote.
        QUOTE_REFUSED (str): A manager sent a submitted quote back.
        PLANNING_RUN_REQUESTED (str): A planning computation was asked for.
        PLANNING_RUN_COMPLETED (str): A planning computation finished.
        COMPANY_CREATED (str): An agency was founded.
        NOTIFICATION_CREATED (str): Notifications were written and their
            recipients may be holding an open event stream.

    Notes:
        - An enumeration rather than string literals scattered across the
          publisher and the consumers, because a routing key typed differently
          in two places does not fail — it binds a queue that never receives
          anything, which looks exactly like a quiet system.
        - **These are the event half of a routing key, never a whole one.**
          Every message is published under ``<value>.<company_id>``; see
          :meth:`scoped_to`. Nothing binds a bare value, so an agency's traffic
          cannot reach another agency's queue.
        - ``COMPANY_CREATED`` is scoped the same way, under the identifier of
          the agency it announces. That keeps the rule uniform — there is no
          "global" event to remember to treat differently — and a worker that
          wants every one of them binds ``company.created.*`` explicitly.
        - ``NOTIFICATION_CREATED`` runs the other way round from the rest: the
          worker publishes it and the **API** consumes it, on a queue of each
          instance's own. It is what turns a written row into a push, and it
          carries recipient identifiers rather than the notifications
          themselves — the reader fetches those over HTTP, from the same
          endpoint it would have used had the push never arrived.
    """

    QUOTE_SUBMITTED = "quote.submitted"
    QUOTE_VALIDATED = "quote.validated"
    QUOTE_REFUSED = "quote.refused"
    PLANNING_RUN_REQUESTED = "planning.run.requested"
    PLANNING_RUN_COMPLETED = "planning.run.completed"
    COMPANY_CREATED = "company.created"
    NOTIFICATION_CREATED = "notification.created"

    def scoped_to(self, company_id: str) -> str:
        """Return the routing key this event takes for one agency.

        Args:
            company_id (str): The agency the event belongs to.

        Returns:
            str: ``"<event>.<company_id>"``.

        Raises:
            MTRoutingKeyMissingCompany: If ``company_id`` is empty.

        Notes:
            The identifier goes last so a binding can select an agency with a
            suffix — ``quote.submitted.<id>`` for one, ``quote.submitted.*``
            for all. Putting it first would make "every event for this agency"
            easy and "this event for every agency" impossible, and the worker
            needs the second one to notice a newly founded agency.

            An empty identifier raises rather than producing ``"quote.submitted."``,
            which is a valid topic key that binds to nothing — the silent
            failure this enumeration exists to prevent, one level down.
        """
        if not company_id:
            raise MTRoutingKeyMissingCompany(
                f"Cannot scope {self.value!r} to an empty company identifier."
            )
        return f"{self.value}.{company_id}"

    @classmethod
    def values(cls) -> Tuple[str, ...]:
        """Return every routing key.

        Returns:
            Tuple[str, ...]: The five supported routing keys.
        """
        return tuple(key.value for key in cls)

    def is_quote_event(self) -> bool:
        """Return whether the key belongs to the quote workflow.

        Returns:
            bool: ``True`` for the three quote topics.
        """
        return self.value.startswith("quote.")
