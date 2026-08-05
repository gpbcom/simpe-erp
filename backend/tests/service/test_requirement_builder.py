from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import Dict, Optional
from unittest.mock import MagicMock

# Third-party imports
import pytest

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import QuoteStatus
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
) -> Customer:
    """Build a customer, optionally without a resolved coordinate.

    Args:
        customer_id (str): The identifier to assign.
        latitude (Optional[float]): The resolved latitude, if any.
        longitude (Optional[float]): The resolved longitude, if any.

    Returns:
        Customer: The customer.
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
        id="quote-1",
        reference="Q-2026-0001",
        customer_id=customer_id,
        status=status,
        lines=[
            QuoteLine(
                id="line-1",
                name=name,
                intervention_type_id="type-1",
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
        settings=MagicMock(),
        config=PlanningConfig(),
    )


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
        self, builder: PlanningService, customers: Dict[str, Customer]
    ) -> None:
        """One accepted line yields one piece of work."""
        requirements = builder.build([_quote()], customers, MONDAY, PERIOD_END)

        assert len(requirements) == 1
        assert requirements[0].quote_line_id == "line-1"

    def test_the_name_and_type_ride_through_untouched(
        self, builder: PlanningService, customers: Dict[str, Customer]
    ) -> None:
        """What was sold is what gets planned.

        Notes:
            The solver decides only *who* and *when*. If either of these were
            lost here, a scheduled slot would arrive at the assistant's phone
            with no indication of what to do.
        """
        requirements = builder.build([_quote()], customers, MONDAY, PERIOD_END)

        assert requirements[0].name == "Toilette matin"
        assert requirements[0].intervention_type_id == "type-1"

    def test_the_window_is_converted_to_minutes(
        self, builder: PlanningService, customers: Dict[str, Customer]
    ) -> None:
        """09:00–13:00 becomes 540–780, the solver's unit."""
        requirements = builder.build([_quote()], customers, MONDAY, PERIOD_END)

        assert requirements[0].window_start_minute == 540
        assert requirements[0].window_end_minute == 780
        assert requirements[0].duration_minutes == 120

    def test_the_customers_coordinate_is_attached(
        self, builder: PlanningService, customers: Dict[str, Customer]
    ) -> None:
        """Work carries where it happens, so it can be routed to."""
        requirements = builder.build([_quote()], customers, MONDAY, PERIOD_END)

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
            builder.build([_quote(status=status)], customers, MONDAY, PERIOD_END) == []
        )

    def test_work_outside_the_period_is_left_alone(
        self, builder: PlanningService, customers: Dict[str, Customer]
    ) -> None:
        """A line next week is not pulled into this week's plan."""
        quote = _quote(service_date=NEXT_MONDAY)

        assert builder.build([quote], customers, MONDAY, PERIOD_END) == []

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

        assert builder.build([_quote()], customers, MONDAY, PERIOD_END) == []

    def test_a_quote_for_an_unknown_customer_is_dropped(
        self, builder: PlanningService
    ) -> None:
        """A quote whose customer is missing yields nothing, not a crash."""
        assert builder.build([_quote()], {}, MONDAY, PERIOD_END) == []

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
        service_date: date,
    ) -> None:
        """Both ends of the requested window are planned.

        Args:
            builder (PlanningService): The builder under test.
            customers (Dict[str, Customer]): The customers behind the quotes.
            service_date (date): The boundary day to check.
        """
        quote = _quote(service_date=service_date)

        assert len(builder.build([quote], customers, MONDAY, PERIOD_END)) == 1

    def test_several_quotes_are_gathered_into_one_list(
        self, builder: PlanningService
    ) -> None:
        """Work for every customer lands in a single plan."""
        customers = {"customer-1": _customer(), "customer-2": _customer("customer-2")}
        quotes = [
            _quote(name="First"),
            _quote(customer_id="customer-2", name="Second"),
        ]

        requirements = builder.build(quotes, customers, MONDAY, PERIOD_END)
        assert sorted(requirement.name for requirement in requirements) == [
            "First",
            "Second",
        ]

    def test_nothing_to_plan_yields_an_empty_list(
        self, builder: PlanningService
    ) -> None:
        """No accepted work is a warning, not an error."""
        assert builder.build([], {}, MONDAY, PERIOD_END) == []
