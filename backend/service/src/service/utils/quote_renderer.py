from __future__ import annotations

# Standard library imports
from decimal import Decimal
from io import BytesIO
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third-party imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# First-party imports
from models.organisation.companies.company import Company
from models.enums import Language
from models.people.customer import Customer
from models.quoting.quote import Quote
from service.quotes.exceptions import MTQuoteNotPriced
from service.utils.exceptions import MTQuoteRenderFailed
from service.utils.formatter import Formatter


class QuoteRenderer:
    """Renders one quote as a PDF a household can read and keep.

    Attributes:
        LABELS (ClassVar[Dict[Language, Dict[str, str]]]): Wording per language.
        HEADERS (ClassVar[Dict[Language, Tuple[str, ...]]]): Line-table column
            headings per language.
        PAGE_SIZE (ClassVar[Tuple[float, float]]): The page dimensions.
        MARGIN (ClassVar[float]): Margin on every side.
        LOGO_WIDTH (ClassVar[float]): Width the agency's logo is drawn at.
        LOGO_HEIGHT (ClassVar[float]): Height the agency's logo is drawn at.
        COLUMN_WIDTHS (ClassVar[Tuple[float, ...]]): Width of each line column.
        styles: The reportlab stylesheet the document is laid out with.
        logger (Logger): Logger for rendering.

    Notes:
        - **The twin of
          :class:`~service.utils.invoice_renderer.InvoiceRenderer`**, and
          deliberately so: a household downloads both from the same screen, and
          two documents that look like different products are two documents
          somebody rings up about. The page furniture, margins and money
          formatting are the same on purpose.
        - **It does not replace ``Formatter.format_quote``.** That renders the
          *Excel* workbook the quote email attaches, has a live caller, and is a
          different artefact for a different audience — a manager who wants to
          re-cost a line. This produces the document the customer reads.
        - **Two real differences from an invoice**, both consequences of a quote
          being an offer rather than a record:

          - *The totals are summed here.* A :class:`~models.quoting.quote.Quote`
            carries no totals of its own. The amounts live on its lines. A bill
            stores its own, because an invoice must reproduce exactly what was
            charged even if the lines are later re-costed.
          - *The customer is read live.* A bill copies the name and address at
            issue, so a household that moves cannot change where last quarter's
            invoice says it was sent. A quote has no such copies, so this takes
            the record as it stands — which is the right answer for an offer
            that has not been agreed yet, and the reason the customer is a
            parameter here rather than a detail on the document.
        - An unpriced quote is **refused**, not printed with blank amounts. See
          :class:`~service.quotes.exceptions.MTQuoteNotPriced`, which the
          API already maps to 422 — the offer is not ready, which is not a
          server error.
    """

    LABELS: ClassVar[Dict[Language, Dict[str, str]]] = {
        Language.FR: {
            "title": "DEVIS",
            "number": "Devis n°",
            "issued_on": "Date du devis",
            "valid_until": "Validité",
            "issued_by": "Émetteur",
            "quoted_to": "Destinataire",
            "no_line": "Ce devis ne comporte aucune prestation.",
            "untaxed": "Total HT",
            "tax": "TVA",
            "grand_total": "Total TTC",
            "legal_heading": "Conditions",
            "acceptance": (
                "Devis valable jusqu'à la date indiquée ci-dessus. "
                "L'acceptation vaut commande et engage les deux parties."
            ),
            "no_validity": (
                "Aucune date de validité n'a été fixée : ce devis peut être "
                "retiré à tout moment."
            ),
            "sap_credit": (
                "Les sommes versées ouvrent droit au crédit d'impôt prévu à "
                "l'article 199 sexdecies du code général des impôts."
            ),
        },
        Language.EN: {
            "title": "QUOTATION",
            "number": "Quotation no.",
            "issued_on": "Quotation date",
            "valid_until": "Valid until",
            "issued_by": "Issued by",
            "quoted_to": "Quoted to",
            "no_line": "This quotation carries no service.",
            "untaxed": "Total excl. VAT",
            "tax": "VAT",
            "grand_total": "Total incl. VAT",
            "legal_heading": "Terms",
            "acceptance": (
                "This quotation is valid until the date shown above. "
                "Acceptance constitutes an order binding on both parties."
            ),
            "no_validity": (
                "No validity date has been set: this quotation may be "
                "withdrawn at any time."
            ),
            "sap_credit": (
                "Amounts paid qualify for the tax credit provided for by "
                "article 199 sexdecies of the French general tax code."
            ),
        },
    }

    HEADERS: ClassVar[Dict[Language, Tuple[str, ...]]] = {
        Language.FR: ("Date", "Prestation", "Durée", "Taux horaire", "Total HT"),
        Language.EN: ("Date", "Service", "Duration", "Hourly rate", "Total excl."),
    }

    PAGE_SIZE: ClassVar[Tuple[float, float]] = A4
    MARGIN: ClassVar[float] = 15 * mm
    LOGO_WIDTH: ClassVar[float] = 45 * mm
    LOGO_HEIGHT: ClassVar[float] = 15 * mm
    COLUMN_WIDTHS: ClassVar[Tuple[float, ...]] = (
        24 * mm,
        66 * mm,
        20 * mm,
        30 * mm,
        30 * mm,
    )

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the renderer.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.styles = getSampleStyleSheet()
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("QuoteRenderer created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _money(self, amount: Decimal) -> str:
        """Return an amount as it is printed.

        Args:
            amount (Decimal): The amount to format.

        Returns:
            str: The amount with two decimals and a euro sign.

        Notes:
            The same shape the invoice prints, because a household compares the
            quote with the invoice that follows it and a difference in
            formatting reads as a difference in figures.
        """
        return f"{amount:.2f} €"

    def _totals_of(self, quote: Quote) -> Tuple[Decimal, Decimal, Decimal]:
        """Return the quote's totals, summed from its lines.

        Args:
            quote (Quote): The quote being rendered.

        Returns:
            Tuple[Decimal, Decimal, Decimal]: Untaxed, tax and gross totals.

        Raises:
            MTQuoteNotPriced: If any line carries no amount.

        Notes:
            **Summed rather than stored**, unlike an invoice. The amounts belong
            to the lines, and a quote re-priced after a rate change must print
            the new figures — an offer describes what the work would cost now,
            where an invoice records what it did cost then.
        """
        untaxed = Decimal("0.00")
        tax = Decimal("0.00")
        gross = Decimal("0.00")
        for line in quote.lines:
            if line.total_ht is None or line.total_ttc is None:
                self.logger.error(
                    "Quote %s carries a line (%s) with no amount. It has not "
                    "been priced and cannot be printed.",
                    quote.reference,
                    line.name,
                )
                raise MTQuoteNotPriced(
                    f"Quote {quote.reference!r} has not been priced. The line "
                    f"{line.name!r} carries no amount."
                )
            untaxed += line.total_ht
            tax += line.vat_amount or Decimal("0.00")
            gross += line.total_ttc
        self.logger.debug(
            "Quote %s totals %s HT, %s TVA, %s TTC.",
            quote.reference,
            untaxed,
            tax,
            gross,
        )
        return untaxed, tax, gross

    def _logo(self, logo: Optional[bytes]) -> Optional[Image]:
        """Return the agency's logo as a drawable, when there is one.

        Args:
            logo (Optional[bytes]): The image bytes, or ``None``.

        Returns:
            Optional[Image]: The drawable, or ``None`` when there is none usable.

        Notes:
            **Reports rather than raises**, as the invoice renderer does. A
            document without its letterhead is still a readable offer; one that
            was never produced is a download button that answers an error.
        """
        if not logo:
            self.logger.debug("No logo was supplied. The quote prints without one.")
            return None
        try:
            return Image(BytesIO(logo), width=self.LOGO_WIDTH, height=self.LOGO_HEIGHT)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            self.logger.warning(
                "Could not draw the agency's logo (%s). The quote prints without it.",
                exc,
            )
            return None

    def _header(
        self,
        quote: Quote,
        company: Company,
        labels: Dict[str, str],
        logo: Optional[bytes],
    ) -> List[Flowable]:
        """Return the title block and the issuer's identity.

        Args:
            quote (Quote): The quote being rendered.
            company (Company): The agency issuing it.
            labels (Dict[str, str]): The wording for the language.
            logo (Optional[bytes]): The agency's logo, when it has one.

        Returns:
            List[Flowable]: The drawables, in printing order.

        Notes:
            The validity date is printed even when absent, saying so in words.
            A blank field beside "valid until" reads as an offer with no end,
            which is the opposite of what an unset date means commercially.
        """
        drawables: List[Flowable] = []
        drawn_logo = self._logo(logo)
        if drawn_logo is not None:
            drawables.append(drawn_logo)
        drawables.append(Paragraph(labels["title"], self.styles["Title"]))
        issued = f"{quote.issued_on:%d/%m/%Y}" if quote.issued_on else "—"
        validity = (
            f"{quote.valid_until:%d/%m/%Y}"
            if quote.valid_until
            else labels["no_validity"]
        )
        if quote.valid_until is None:
            self.logger.warning(
                "Quote %s has no validity date. The document says so rather "
                "than leaving the field blank.",
                quote.reference,
            )
        drawables.append(
            Paragraph(
                f"{labels['number']} {quote.reference}<br/>"
                f"{labels['issued_on']} : {issued}<br/>"
                f"{labels['valid_until']} : {validity}",
                self.styles["BodyText"],
            )
        )
        identity = Formatter.describe_company(company, labels)
        drawables.append(
            Paragraph(
                f"<b>{labels['issued_by']}</b><br/>"
                f"{Formatter.trading_name(company)}<br/>{identity}",
                self.styles["BodyText"],
            )
        )
        if not identity:
            self.logger.warning(
                "Quote %s is being issued by an agency with no address, "
                "registration number or contact details. The document will not "
                "identify its issuer.",
                quote.reference,
            )
        return drawables

    def _parties(self, customer: Customer, labels: Dict[str, str]) -> List[Flowable]:
        """Return the block naming who the quote is addressed to.

        Args:
            customer (Customer): The household the offer is for.
            labels (Dict[str, str]): The wording for the language.

        Returns:
            List[Flowable]: The drawables, in printing order.

        Notes:
            Read from the **live** record, unlike an invoice, which prints its
            own copies. A quote is an offer that has not been agreed. If the
            household has moved since it was written, the offer is for the
            address they live at now.
        """
        return [
            Paragraph(
                f"<b>{labels['quoted_to']}</b><br/>"
                f"{customer.full_name()}<br/>"
                f"{customer.address.to_single_line()}",
                self.styles["BodyText"],
            )
        ]

    def _lines_table(self, quote: Quote, language: Language) -> Table:
        """Return the table of services the quote offers.

        Args:
            quote (Quote): The quote being rendered.
            language (Language): The language the headings are written in.

        Returns:
            Table: The drawable table.

        Notes:
            A quote with no line still prints a table saying so. An offer that
            silently shows nothing is one a household reads as an error.
        """
        headers = self.HEADERS[language]
        rows: List[List[str]] = [list(headers)]
        if not quote.lines:
            self.logger.warning(
                "Quote %s carries no line. The document says so.", quote.reference
            )
            rows.append([self.LABELS[language]["no_line"], "", "", "", ""])
        for line in quote.lines:
            rate = line.hourly_rate_ht
            rows.append(
                [
                    f"{line.service_date:%d/%m/%Y}",
                    line.name,
                    f"{line.duration_minutes} min",
                    self._money(rate) if rate is not None else "—",
                    self._money(line.total_ht) if line.total_ht is not None else "—",
                ]
            )
        table = Table(rows, colWidths=self.COLUMN_WIDTHS, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        return table

    def _totals(self, quote: Quote, labels: Dict[str, str]) -> Table:
        """Return the totals block.

        Args:
            quote (Quote): The quote being rendered.
            labels (Dict[str, str]): The wording for the language.

        Returns:
            Table: The drawable table.

        Raises:
            MTQuoteNotPriced: If any line carries no amount.
        """
        untaxed, tax, gross = self._totals_of(quote)
        rows = [
            [labels["untaxed"], self._money(untaxed)],
            [labels["tax"], self._money(tax)],
            [labels["grand_total"], self._money(gross)],
        ]
        table = Table(rows, colWidths=(60 * mm, 30 * mm), hAlign="RIGHT")
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
                ]
            )
        )
        return table

    def _legal(self, labels: Dict[str, str]) -> List[Flowable]:
        """Return the terms printed under the totals.

        Args:
            labels (Dict[str, str]): The wording for the language.

        Returns:
            List[Flowable]: The drawables, in printing order.

        Notes:
            Shorter than an invoice's block, and the difference is real: late
            payment penalties and the recovery indemnity belong on a document
            that is *due*, not on an offer. What a quote must say is how long it
            stands and what accepting it means.
        """
        return [
            Paragraph(f"<b>{labels['legal_heading']}</b>", self.styles["BodyText"]),
            Paragraph(labels["acceptance"], self.styles["BodyText"]),
            Paragraph(labels["sap_credit"], self.styles["BodyText"]),
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    def render(
        self,
        quote: Quote,
        customer: Customer,
        company: Company,
        language: Language = Language.FR,
        logo: Optional[bytes] = None,
    ) -> bytes:
        """Render one quote as a PDF.

        Args:
            quote (Quote): The quote to render, priced.
            customer (Customer): The household it is addressed to.
            company (Company): The agency issuing it.
            language (Language): The language to write it in. Defaults to
                French.
            logo (Optional[bytes]): The agency's logo, when it has one.

        Returns:
            bytes: The rendered document.

        Raises:
            MTQuoteNotPriced: If the quote has not been priced.
            MTQuoteRenderFailed: If the document could not be laid out.

        Notes:
            The customer is used **on the page**, not only in the log — which is
            the one signature difference from the invoice renderer, and it
            follows from a quote carrying no copy of the name and address it is
            addressed to.
        """
        labels = self.LABELS[language]
        self.logger.debug(
            "Rendering quote %s for customer %s (%d line(s), %s).",
            quote.reference,
            customer.id,
            len(quote.lines),
            language.value,
        )
        buffer = BytesIO()
        drawables: List[Flowable] = []
        drawables.extend(self._header(quote, company, labels, logo))
        drawables.append(Spacer(1, 4 * mm))
        drawables.extend(self._parties(customer, labels))
        drawables.append(Spacer(1, 6 * mm))
        drawables.append(self._lines_table(quote, language))
        drawables.append(Spacer(1, 4 * mm))
        drawables.append(self._totals(quote, labels))
        drawables.append(Spacer(1, 6 * mm))
        drawables.extend(self._legal(labels))
        try:
            document = SimpleDocTemplate(
                buffer,
                pagesize=self.PAGE_SIZE,
                topMargin=self.MARGIN,
                bottomMargin=self.MARGIN,
                leftMargin=self.MARGIN,
                rightMargin=self.MARGIN,
                title=f"{labels['title']} {quote.reference}",
                author=Formatter.trading_name(company),
            )
            document.build(drawables)
        except Exception as exc:  # noqa: BLE001 - reported as a render failure
            self.logger.error("Could not render quote %s: %s.", quote.reference, exc)
            raise MTQuoteRenderFailed(
                f"Could not render quote {quote.reference}: {exc}."
            ) from exc
        payload = buffer.getvalue()
        self.logger.info(
            "Rendered quote %s as %d bytes.", quote.reference, len(payload)
        )
        return payload
