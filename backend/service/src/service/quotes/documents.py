from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import Optional, Tuple

# First-party imports
from models.enums import Language
from service.quotes.exceptions import MTQuoteNotFound
from service.quotes.quotes import QuoteService
from service.utils.quote_renderer import QuoteRenderer
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.people.customer import CustomerRepository
from storage.s3.s3_storage import S3Storage


class QuoteDocumentService:
    """Produces the PDF a household downloads for one quote.

    Attributes:
        quotes (QuoteService): Reads the quote.
        customers (CustomerRepository): Reads who it is addressed to.
        companies (CompanyRepository): Reads who issues it.
        renderer (QuoteRenderer): Lays the document out.
        logos (Optional[S3Storage]): The object store holding agency logos.
        logger (Logger): Logger for document operations.

    Notes:
        - **Rendered on demand, never stored**, and that is the one real
          difference from an invoice. A bill's PDF is written to the object
          store when the bill is generated, because an invoice must reproduce
          exactly what was sent however the underlying records change. A quote
          is still an offer: it is re-priced when a rate changes, its lines are
          edited, it may be rescheduled by the household. A stored file would go
          stale silently and a customer would download last week's prices.
        - A class of its own rather than another method on
          :class:`~service.quotes.quotes.QuoteService`. Producing the document
          needs the customer, the agency and the object store — three
          collaborators that pricing and validation have no use for, and adding
          them to that constructor would make every caller carry them.
    """

    def __init__(
        self,
        quotes: QuoteService,
        customers: CustomerRepository,
        companies: CompanyRepository,
        renderer: QuoteRenderer,
        logos: Optional[S3Storage] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            quotes (QuoteService): The quote service.
            customers (CustomerRepository): The customer store.
            companies (CompanyRepository): The agency store.
            renderer (QuoteRenderer): The document renderer.
            logos (Optional[S3Storage]): The object store holding logos.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.quotes = quotes
        self.customers = customers
        self.companies = companies
        self.renderer = renderer
        self.logos = logos
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("QuoteDocumentService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _logo(self, logo_url: Optional[str]) -> Optional[bytes]:
        """Read the agency's logo, best effort.

        Args:
            logo_url (Optional[str]): Where the logo lives, when there is one.

        Returns:
            Optional[bytes]: The image bytes, or ``None``.

        Notes:
            **Every failure is a ``None``, never an exception.** A household is
            waiting for their offer; withholding it because a decoration could
            not be fetched would be the wrong trade, and the renderer already
            prints a complete document without one.
        """
        if not logo_url or self.logos is None:
            self.logger.debug("No logo to fetch. The quote prints without one.")
            return None
        try:
            return await self.logos.fetch_logo(logo_url)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            self.logger.warning(
                "Could not read the agency's logo (%s). The quote prints without it.",
                exc,
            )
            return None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def document(
        self, quote_id: str, language: Language = Language.FR
    ) -> Tuple[bytes, str]:
        """Render one quote as a PDF, with the filename to serve it under.

        Args:
            quote_id (str): The quote to render.
            language (Language): The language to write it in.

        Returns:
            Tuple[bytes, str]: The document, and its filename.

        Raises:
            MTQuoteNotFound: If no such quote exists, or its customer or agency
                no longer does.
            MTQuoteNotPriced: If it has never been priced. A 422.
            MTQuoteRenderFailed: If the document could not be laid out.

        Notes:
            The filename is derived from the quote's reference and never from
            anything a caller sends — the same rule the invoice download
            follows, and the reason neither can be talked into writing outside
            its own name.
        """
        self.logger.debug("Rendering the document of quote %s.", quote_id)
        quote = await self.quotes.get(quote_id)

        customer = await self.customers.get(quote.customer_id)
        if customer is None:
            self.logger.error(
                "Quote %s names customer %s, which no longer exists. The "
                "document cannot say who it is addressed to.",
                quote.reference,
                quote.customer_id,
            )
            raise MTQuoteNotFound(
                f"Quote {quote.reference!r} names a customer that no longer exists."
            )

        company = await self.companies.get(quote.company_id)
        if company is None:
            self.logger.error(
                "Quote %s names agency %s, which no longer exists. The "
                "document would identify no issuer.",
                quote.reference,
                quote.company_id,
            )
            raise MTQuoteNotFound(
                f"Quote {quote.reference!r} names an agency that no longer exists."
            )

        if not quote.status.is_editable():
            self.logger.info(
                "Quote %s is %s. The document reflects the offer as it stands "
                "now, not as it was when it was sent.",
                quote.reference,
                quote.status.value,
            )
        logo = await self._logo(company.logo_url)
        payload = self.renderer.render(
            quote=quote,
            customer=customer,
            company=company,
            language=language,
            logo=logo,
        )
        filename = f"{quote.reference}.pdf"
        self.logger.info("Serving %d bytes of quote %s.", len(payload), filename)
        return payload, filename
