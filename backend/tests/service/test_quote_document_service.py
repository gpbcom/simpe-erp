from __future__ import annotations

# Standard library imports
from unittest.mock import AsyncMock, Mock

# Third-party imports
import pytest

# First-party imports
from models.organisation.companies.company import Company
from models.enums import Language
from models.people.customer import Customer
from models.quoting.quote import Quote
from service.quotes.documents import QuoteDocumentService
from service.quotes.exceptions import MTQuoteNotFound


def _customer() -> Customer:
    """Build the household the offer is for.

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


def _company(logo_url: str = None) -> Company:
    """Build the agency issuing the offer.

    Args:
        logo_url (str): Where its logo lives, when it has one.

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
        logo_url=logo_url,
    )


@pytest.fixture
def quotes() -> AsyncMock:
    """Return a stand-in quote service.

    Returns:
        AsyncMock: The service double.
    """
    service = AsyncMock()
    service.get.return_value = Quote(
        company_id="company-1",
        id="quote-1",
        reference="Q-2026-0001",
        customer_id="customer-1",
    )
    return service


@pytest.fixture
def service(quotes: AsyncMock) -> QuoteDocumentService:
    """Return the document service over stand-in collaborators.

    Args:
        quotes (AsyncMock): The quote service double.

    Returns:
        QuoteDocumentService: The service under test.
    """
    customers = AsyncMock()
    customers.get.return_value = _customer()
    companies = AsyncMock()
    companies.get.return_value = _company()
    renderer = Mock()
    renderer.render.return_value = b"%PDF-1.4 fake"
    return QuoteDocumentService(
        quotes=quotes,
        customers=customers,
        companies=companies,
        renderer=renderer,
        logos=None,
    )


class TestQuoteDocumentService:
    """Tests for producing the PDF a household downloads."""

    async def test_it_returns_the_document_and_its_name(
        self, service: QuoteDocumentService
    ) -> None:
        """The filename comes from the quote's own reference.

        Notes:
            Never from anything a caller sends — the same rule the invoice
            download follows, and the reason neither can be talked into writing
            outside its own name.
        """
        payload, filename = await service.document("quote-1")

        assert payload.startswith(b"%PDF-")
        assert filename == "Q-2026-0001.pdf"

    async def test_the_language_reaches_the_renderer(
        self, service: QuoteDocumentService
    ) -> None:
        """A household reads their offer in their own language."""
        await service.document("quote-1", language=Language.EN)

        assert service.renderer.render.call_args.kwargs["language"] is Language.EN

    async def test_an_absent_household_is_reported(
        self, service: QuoteDocumentService
    ) -> None:
        """A document cannot say who it is addressed to.

        Notes:
            Refused rather than printed with a blank recipient. A quote with no
            addressee is not a lesser document, it is not a document.
        """
        service.customers.get.return_value = None

        with pytest.raises(MTQuoteNotFound):
            await service.document("quote-1")

    async def test_an_absent_agency_is_reported(
        self, service: QuoteDocumentService
    ) -> None:
        """A document that identifies no issuer is not a valid offer."""
        service.companies.get.return_value = None

        with pytest.raises(MTQuoteNotFound):
            await service.document("quote-1")

    async def test_a_missing_object_store_prints_without_a_logo(
        self, service: QuoteDocumentService
    ) -> None:
        """**A decoration must never withhold the offer.**

        Notes:
            A deployment with no object store still issues quotes; they simply
            arrive without a letterhead.
        """
        payload, _ = await service.document("quote-1")

        assert payload.startswith(b"%PDF-")
        assert service.renderer.render.call_args.kwargs["logo"] is None

    async def test_an_unreadable_logo_does_not_fail_the_download(
        self, quotes: AsyncMock
    ) -> None:
        """Every logo failure is a ``None``, never an exception."""
        logos = AsyncMock()
        logos.fetch_logo.side_effect = RuntimeError("bucket unreachable")
        customers = AsyncMock()
        customers.get.return_value = _customer()
        companies = AsyncMock()
        companies.get.return_value = _company(
            logo_url="https://example.test/company-logos/company-1.png"
        )
        renderer = Mock()
        renderer.render.return_value = b"%PDF-1.4 fake"
        service = QuoteDocumentService(
            quotes=quotes,
            customers=customers,
            companies=companies,
            renderer=renderer,
            logos=logos,
        )

        payload, _ = await service.document("quote-1")

        assert payload.startswith(b"%PDF-")
        assert renderer.render.call_args.kwargs["logo"] is None
