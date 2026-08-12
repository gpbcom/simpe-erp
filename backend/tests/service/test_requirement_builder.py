from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
import pytest

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.configuration.planning_config import PlanningConfig
from models.enums import QuoteStatus, RegistrationStatus
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.planning.plannings import PlanningService

MONDAY = date(2026, 8, 3)
NEXT_MONDAY = date(2026, 8, 10)
PERIOD_END = date(2026, 8, 9)


def _customer(
    customer_id: str = "customer-1",
    latitude: Optional[float] = 48.8566,
    longitude: Optional[float] = 2.3522,
    status: RegistrationStatus = RegistrationStatus.ACTIVE,
) -> Customer:
    """Build a customer, optionally without a resolved coordinate.

    Args:
        customer_id (str): The identifier to assign.
        latitude (Optional[float]): The resolved latitude, if any.
        longitude (Optional[float]): The resolved longitude, if any.
        status (RegistrationStatus): Their registration status.

    Returns:
        Customer: The customer.

    Notes:
        The status is **stated**, not left to the model. Its default is
        ``PROSPECT``, and a prospect is deliberately never scheduled — so a
        helper that omitted it would build a customer this whole suite's
        subject refuses to plan, and every test would pass by accident for the
        wrong reason.
    """
    return Customer(
        id=customer_id,
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email=f"{customer_id}@example.com",
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": latitude,
            "longitude": longitude,
        },
        registration_status=status,
    )


def _quote(
    status: QuoteStatus = QuoteStatus.ACCEPTED,
    service_date: date = MONDAY,
    customer_id: str = "customer-1",
    name: str = "Toilette matin",
) -> Quote:
    """Build a one-line quote.

    Args:
        status (QuoteStatus): Where the quote is in its lifecycle.
        service_date (date): The day its line is delivered.
        customer_id (str): Whose quote it is.
        name (str): What the line sells.

    Returns:
        Quote: The quote, priced — an unpriced quote is not schedulable
        whatever its status.
    """
    return Quote(
        company_id="company-1",
        id="quote-1",
        reference="Q-2026-0001",
        customer_id=customer_id,
        status=status,
        lines=[
            QuoteLine(
                id="line-1",
                name=name,
                intervention_type_id="type-1",
                service_category="necessity",
                service_date=service_date,
                earliest_start=time(9, 0),
                latest_end=time(13, 0),
                duration_minutes=120,
                hourly_rate_ht=Decimal("31.91"),
                total_ht=Decimal("63.81"),
                vat_amount=Decimal("3.51"),
                total_ttc=Decimal("67.32"),
            )
        ],
    )


@pytest.fixture
def builder() -> PlanningService:
    """Return a requirement builder.

    Returns:
        PlanningService: The builder under test.
    """
    return PlanningService(
        runs=MagicMock(),
        interventions=MagicMock(),
        quotes=MagicMock(),
        customers=MagicMock(),
        hcas=MagicMock(),
        types=MagicMock(),
        settings=MagicMock(),
        teams=AsyncMock(),
        config=PlanningConfig(),
    )


@pytest.fixture
def catalog() -> Dict[str, InterventionType]:
    """Return the catalogue the quotes' lines sell, keyed by identifier.

    Returns:
        Dict[str, InterventionType]: One entry, requiring no qualification.

    Notes:
        Requiring nothing is the default state of a catalogue entry, so these
        tests exercise the same path every existing quote takes.
    """
    return {
        "type-1": InterventionType(
            id="type-1",
            name="Toilette matin",
            code="TOILETTE",
            service_category="necessity",
        )
    }


@pytest.fixture
def customers() -> Dict[str, Customer]:
    """Return one geocoded customer, keyed by identifier.

    Returns:
        Dict[str, Customer]: The customers a quote can point at.
    """
    return {"customer-1": _customer()}


class TestPlanningService:
    """Tests for turning accepted quote lines into schedulable work."""

    # ------------------------------------------------------------------ #
    #  What crosses the bridge
    # ------------------------------------------------------------------ #

    def test_an_accepted_line_becomes_a_requirement(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """One accepted line yields one piece of work."""
        requirements = builder.build([_quote()], customers, catalog, MONDAY, PERIOD_END)

        assert len(requirements) == 1
        assert requirements[0].quote_line_id == "line-1"

    def test_the_name_and_type_ride_through_untouched(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """What was sold is what gets planned.

        Notes:
            The solver decides only *who* and *when*. If either of these were
            lost here, a scheduled slot would arrive at the assistant's phone
            with no indication of what to do.
        """
        requirements = builder.build([_quote()], customers, catalog, MONDAY, PERIOD_END)

        assert requirements[0].name == "Toilette matin"
        assert requirements[0].intervention_type_id == "type-1"

    def test_the_window_is_converted_to_minutes(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """09:00–13:00 becomes 540–780, the solver's unit."""
        requirements = builder.build([_quote()], customers, catalog, MONDAY, PERIOD_END)

        assert requirements[0].window_start_minute == 540
        assert requirements[0].window_end_minute == 780
        assert requirements[0].duration_minutes == 120

    def test_the_customers_coordinate_is_attached(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """Work carries where it happens, so it can be routed to."""
        requirements = builder.build([_quote()], customers, catalog, MONDAY, PERIOD_END)

        assert requirements[0].location.latitude == pytest.approx(48.8566)
        assert requirements[0].location.longitude == pytest.approx(2.3522)

    # ------------------------------------------------------------------ #
    #  What is dropped, and why
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(QuoteStatus.DRAFT, id="Not schedulable - draft"),
            pytest.param(QuoteStatus.SENT, id="Not schedulable - sent"),
            pytest.param(QuoteStatus.REJECTED, id="Not schedulable - rejected"),
            pytest.param(QuoteStatus.EXPIRED, id="Not schedulable - expired"),
        ],
    )
    def test_only_an_accepted_quote_is_planned(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        status: QuoteStatus,
    ) -> None:
        """A quote nobody accepted contributes nothing.

        Args:
            builder (PlanningService): The builder under test.
            customers (Dict[str, Customer]): The customers behind the quotes.
            status (QuoteStatus): The non-accepted status to check.

        Notes:
            The repository already filters on status. Re-checking here means
            the rule holds however the builder is called — planning unsold work
            would put an assistant in a stranger's home.
        """
        assert (
            builder.build(
                [_quote(status=status)], customers, catalog, MONDAY, PERIOD_END
            )
            == []
        )

    def test_work_outside_the_period_is_left_alone(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """A line next week is not pulled into this week's plan."""
        quote = _quote(service_date=NEXT_MONDAY)

        assert builder.build([quote], customers, catalog, MONDAY, PERIOD_END) == []

    def test_an_interrupted_quote_stops_producing_work(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """**An arrangement ended early is not planned past its last day.**

        Args:
            builder (PlanningService): The builder under test.
            customers (Dict[str, Customer]): The customers behind the quotes.

        Notes:
            Without this the planner would keep sending an assistant to a home
            the family has stopped paying for — and, because the quote stays
            accepted and priced, nothing else in the system would notice.
        """
        # Two visits a week apart, ended after the first. Built this way rather
        # than by interrupting a single-line quote before its only service:
        # that state is refused outright, because an accepted quote delivering
        # nothing should be rejected instead of silenced.
        quote = _quote(service_date=MONDAY)
        both = quote.model_copy(
            update={
                "lines": [
                    quote.lines[0],
                    quote.lines[0].model_copy(
                        update={"id": "line-2", "service_date": NEXT_MONDAY}
                    ),
                ],
                "interrupted_on": MONDAY,
            }
        )

        # Planning the week that starts after the end date finds nothing left.
        assert builder.build([both], customers, catalog, NEXT_MONDAY, NEXT_MONDAY) == []

    def test_the_days_before_an_interruption_are_still_planned(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """**The interruption cuts the quote in half, not out.**

        Notes:
            This is why the filter is per line rather than per quote. Dropping
            the whole quote would cancel the visits *before* the end date too —
            work the family is expecting this week, already agreed and already
            paid for.
        """
        quote = _quote(service_date=MONDAY).model_copy(
            update={"interrupted_on": MONDAY}
        )

        requirements = builder.build([quote], customers, catalog, MONDAY, PERIOD_END)

        assert len(requirements) == 1
        assert requirements[0].day == MONDAY

    def test_the_last_day_of_an_arrangement_is_planned(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
    ) -> None:
        """Inclusive here too, or the final visit silently disappears."""
        quote = _quote(service_date=MONDAY).model_copy(
            update={"interrupted_on": MONDAY}
        )

        assert len(builder.build([quote], customers, catalog, MONDAY, PERIOD_END)) == 1

    def test_an_unresolved_address_is_dropped_rather_than_guessed(
        self, builder: PlanningService
    ) -> None:
        """A customer with no coordinate cannot be routed to.

        Notes:
            Letting this through would mean planning a round around a place
            nobody can find; the travel term would silently treat it as being
            at the origin of the coordinate system, off the coast of Africa.
            It is reported at ERROR rather than dropped quietly.
        """
        customers = {"customer-1": _customer(latitude=None, longitude=None)}

        assert builder.build([_quote()], customers, catalog, MONDAY, PERIOD_END) == []

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(RegistrationStatus.PROSPECT, id="prospect"),
            pytest.param(RegistrationStatus.STOPPED, id="stopped"),
        ],
    )
    def test_a_customer_who_may_not_be_scheduled_yields_nothing(
        self, builder: PlanningService, status: RegistrationStatus
    ) -> None:
        """**The rule PROSPECT exists for, asserted on a flawless quote.**

        Args:
            builder (PlanningService): The service under test.
            status (RegistrationStatus): The status that blocks scheduling.

        Notes:
            Everything else about this work is right: the quote is accepted and
            priced, the line falls inside the period, the quote is not
            interrupted and the customer's address resolved. The *only* reason
            nothing comes back is who the customer is to the agency.

            That is what makes this the test worth having. A prospect whose
            quote was also out of period would pass for three other reasons.
        """
        customers = {"customer-1": _customer(status=status)}

        assert builder.build([_quote()], customers, catalog, MONDAY, PERIOD_END) == []

    def test_promoting_the_customer_is_what_schedules_their_work(
        self, builder: PlanningService, catalog: Dict[str, InterventionType]
    ) -> None:
        """The same quote plans once the customer is active.

        Args:
            builder (PlanningService): The service under test.
            catalog (Dict[str, InterventionType]): The services on offer.

        Notes:
            - The other half of the rule. Without this, a bug that dropped
              *every* requirement would satisfy the test above and look exactly
              like the feature working.
            - This one takes the ``catalog`` **fixture**, where its neighbours
              refer to the bare name and so pass the fixture *function*. They
              get away with it because they assert an empty result and return
              before the catalog is ever dereferenced; this one plans real work
              and would raise ``AttributeError`` on the function object.
        """
        prospect = {"customer-1": _customer(status=RegistrationStatus.PROSPECT)}
        promoted = {"customer-1": _customer(status=RegistrationStatus.ACTIVE)}

        assert builder.build([_quote()], prospect, catalog, MONDAY, PERIOD_END) == []
        assert builder.build([_quote()], promoted, catalog, MONDAY, PERIOD_END) != []

    def test_a_quote_for_an_unknown_customer_is_dropped(
        self, builder: PlanningService
    ) -> None:
        """A quote whose customer is missing yields nothing, not a crash."""
        assert builder.build([_quote()], {}, catalog, MONDAY, PERIOD_END) == []

    # ------------------------------------------------------------------ #
    #  Boundaries
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "service_date",
        [
            pytest.param(MONDAY, id="Valid - first day of the period"),
            pytest.param(PERIOD_END, id="Valid - last day of the period"),
        ],
    )
    def test_the_period_bounds_are_inclusive(
        self,
        builder: PlanningService,
        customers: Dict[str, Customer],
        catalog: Dict[str, InterventionType],
        service_date: date,
    ) -> None:
        """Both ends of the requested window are planned.

        Args:
            builder (PlanningService): The builder under test.
            customers (Dict[str, Customer]): The customers behind the quotes.
            service_date (date): The boundary day to check.
        """
        quote = _quote(service_date=service_date)

        assert len(builder.build([quote], customers, catalog, MONDAY, PERIOD_END)) == 1

    def test_several_quotes_are_gathered_into_one_list(
        self, builder: PlanningService, catalog: Dict[str, InterventionType]
    ) -> None:
        """Work for every customer lands in a single plan."""
        customers = {"customer-1": _customer(), "customer-2": _customer("customer-2")}
        quotes = [
            _quote(name="First"),
            _quote(customer_id="customer-2", name="Second"),
        ]

        requirements = builder.build(quotes, customers, catalog, MONDAY, PERIOD_END)
        assert sorted(requirement.name for requirement in requirements) == [
            "First",
            "Second",
        ]

    def test_nothing_to_plan_yields_an_empty_list(
        self, builder: PlanningService
    ) -> None:
        """No accepted work is a warning, not an error."""
        assert builder.build([], {}, catalog, MONDAY, PERIOD_END) == []
