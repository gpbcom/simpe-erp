from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

# Third-party imports
import pytest

# First-party imports
from models.organisation.companies.company import Company
from models.enums import Language
from models.people.customer import Customer
from models.quoting.quote import Quote
from service.quotes.exceptions import MTQuoteNotPriced
from service.utils.quote_renderer import QuoteRenderer
from tests.annotations import ModelInput


def _line(priced: bool = True, **overrides: ModelInput) -> Dict[str, ModelInput]:
    """Build a quote line.

    Args:
        priced (bool): Whether the amounts have been computed.
        **overrides (ModelInput): Fields to replace.

    Returns:
        Dict[str, ModelInput]: The line, as the model takes it.
    """
    amounts: Dict[str, ModelInput] = (
        {
            "hourly_rate_ht": Decimal("25.00"),
            "total_ht": Decimal("25.00"),
            "vat_amount": Decimal("1.38"),
            "total_ttc": Decimal("26.38"),
        }
        if priced
        else {}
    )
    return {
        "id": "line-1",
        "name": "Toilette",
        "intervention_type_id": "type-1",
        "service_category": "necessity",
        "service_date": "2026-03-10",
        "earliest_start": "09:00",
        "latest_end": "11:00",
        "duration_minutes": 60,
        **amounts,
        **overrides,
    }


def _quote(
    lines: Optional[List[Dict[str, ModelInput]]] = None, **overrides: ModelInput
) -> Quote:
    """Build a quote.

    Args:
        lines (Optional[List[Dict[str, ModelInput]]]): Its lines, or one priced line.
        **overrides (ModelInput): Fields to replace.

    Returns:
        Quote: The quote.
    """
    return Quote(
        company_id="company-1",
        team_id="team-1",
        id="quote-1",
        reference="Q-2026-0001",
        customer_id="customer-1",
        issued_on=date(2026, 3, 1),
        valid_until=date(2026, 4, 1),
        lines=lines if lines is not None else [_line()],
        **overrides,
    )


@pytest.fixture
def customer() -> Customer:
    """Return the household the offer is for.

    Returns:
        Customer: The household.
    """
    return Customer(
        id="customer-1",
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email="marie.durand@example.com",
        address={
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8558,
            "longitude": 2.3588,
        },
    )


@pytest.fixture
def company() -> Company:
    """Return the agency issuing the offer.

    Returns:
        Company: The agency.
    """
    return Company(
        id="company-1",
        name="Aide et Soins",
        address={
            "street": "1 rue de la Paix",
            "postal_code": "75001",
            "city": "Paris",
            "latitude": 48.8698,
            "longitude": 2.3312,
        },
    )


@pytest.fixture
def renderer() -> QuoteRenderer:
    """Return the renderer under test.

    Returns:
        QuoteRenderer: The renderer.
    """
    return QuoteRenderer()


class TestQuoteRendering:
    """Tests for the document a household downloads."""

    def test_it_produces_a_pdf(
        self, renderer: QuoteRenderer, customer: Customer, company: Company
    ) -> None:
        """The ordinary case produces a real document.

        Notes:
            Asserted on the magic bytes rather than the length. A renderer that
            silently produced an empty or truncated file would still return
            *some* bytes, and a download button that hands back a corrupt PDF is
            indistinguishable from a broken one.
        """
        payload = renderer.render(_quote(), customer, company)

        assert payload.startswith(b"%PDF-")
        assert len(payload) > 500

    @pytest.mark.parametrize("language", list(Language))
    def test_every_language_renders(
        self,
        renderer: QuoteRenderer,
        customer: Customer,
        company: Company,
        language: Language,
    ) -> None:
        """A missing translation would raise a KeyError at download time.

        Args:
            renderer (QuoteRenderer): The renderer under test.
            customer (Customer): The household.
            company (Company): The agency.
            language (Language): The language under test.
        """
        assert renderer.render(_quote(), customer, company, language).startswith(
            b"%PDF-"
        )

    @pytest.mark.parametrize("language", list(Language))
    def test_every_language_has_every_label(
        self, renderer: QuoteRenderer, language: Language
    ) -> None:
        """The two label sets carry the same keys.

        Args:
            renderer (QuoteRenderer): The renderer under test.
            language (Language): The language under test.

        Notes:
            A key present in French and absent in English fails only when
            somebody downloads an English quote — which is exactly the sort of
            thing nobody tries until a customer does.
        """
        assert set(QuoteRenderer.LABELS[language]) == set(
            QuoteRenderer.LABELS[Language.FR]
        )
        assert len(QuoteRenderer.HEADERS[language]) == len(QuoteRenderer.COLUMN_WIDTHS)

    # ------------------------------------------------------------------ #
    #  Pricing
    # ------------------------------------------------------------------ #

    def test_an_unpriced_quote_is_refused(
        self, renderer: QuoteRenderer, customer: Customer, company: Company
    ) -> None:
        """**Refused rather than printed with a blank price.**

        Notes:
            A document showing a service, a date, a duration and an empty
            amount reads as *free*. That is the one mistake on a commercial
            document nobody forgives, and it is worth a refusal the screen can
            explain.
        """
        with pytest.raises(MTQuoteNotPriced):
            renderer.render(_quote(lines=[_line(priced=False)]), customer, company)

    def test_one_unpriced_line_refuses_the_whole_document(
        self, renderer: QuoteRenderer, customer: Customer, company: Company
    ) -> None:
        """A partly-priced quote is not a partly-valid offer."""
        with pytest.raises(MTQuoteNotPriced):
            renderer.render(
                _quote(lines=[_line(), _line(id="line-2", priced=False)]),
                customer,
                company,
            )

    def test_the_totals_are_summed_from_the_lines(
        self, renderer: QuoteRenderer
    ) -> None:
        """**A quote carries no totals of its own**, unlike an invoice.

        Notes:
            A bill stores its own, because it must reproduce what was charged
            however the lines are later re-costed. An offer describes what the
            work would cost *now*, so the figures follow the lines.
        """
        quote = _quote(lines=[_line(), _line(id="line-2")])

        untaxed, tax, gross = renderer._totals_of(quote)

        assert untaxed == Decimal("50.00")
        assert tax == Decimal("2.76")
        assert gross == Decimal("52.76")

    # ------------------------------------------------------------------ #
    #  Degraded cases that must still produce a document
    # ------------------------------------------------------------------ #

    def test_a_quote_with_no_line_still_renders(
        self, renderer: QuoteRenderer, customer: Customer, company: Company
    ) -> None:
        """An offer that shows nothing at all reads as an error.

        Notes:
            The table prints a sentence instead of collapsing, so the household
            sees a document that says what it means.
        """
        assert renderer.render(_quote(lines=[]), customer, company).startswith(b"%PDF-")

    def test_a_corrupt_logo_does_not_stop_the_document(
        self, renderer: QuoteRenderer, customer: Customer, company: Company
    ) -> None:
        """**Reported, never fatal.**

        Notes:
            A document without its letterhead is still a readable offer; one
            that was never produced is a download button that answers an error
            page. Same trade the invoice renderer makes.
        """
        payload = renderer.render(
            _quote(), customer, company, logo=b"this is not an image"
        )

        assert payload.startswith(b"%PDF-")

    def test_a_quote_with_no_validity_date_renders(
        self, renderer: QuoteRenderer, customer: Customer, company: Company
    ) -> None:
        """It says so in words rather than leaving the field blank.

        Notes:
            A blank beside "valid until" reads as an offer with no end, which
            is the opposite of what an unset date means commercially.
        """
        quote = _quote().model_copy(update={"valid_until": None})

        assert renderer.render(quote, customer, company).startswith(b"%PDF-")

    def test_the_household_is_read_live(
        self, renderer: QuoteRenderer, customer: Customer, company: Company
    ) -> None:
        """**The other real difference from an invoice.**

        Notes:
            A bill prints its own copies of the name and address, so a household
            that moves cannot change where last quarter's invoice says it was
            sent. A quote has no copies — it is an offer that has not been
            agreed — so it is addressed to where they live now. Asserted by
            rendering the same quote for two different households and getting
            two different documents.
        """
        moved = customer.model_copy(
            update={"last_name": "Durand-Martin"},
        )

        first = renderer.render(_quote(), customer, company)
        second = renderer.render(_quote(), moved, company)

        assert first != second
