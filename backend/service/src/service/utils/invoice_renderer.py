from __future__ import annotations

# Standard library imports
from decimal import Decimal
from io import BytesIO
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple

# Third-party imports
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
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
from models.billing.bill import Bill
from models.companies.company import Company
from models.enums import Language
from models.people.customer import Customer
from models.settings.billing_settings import BillingSettings
from service.utils.exceptions import MTInvoiceRenderFailed
from service.utils.formatter import Formatter


class InvoiceRenderer:
    """Lays out a bill as the PDF a French customer is legally owed.

    Attributes:
        FONT (ClassVar[str]): The embedded typeface the document is set in.
        BOLD_FONT (ClassVar[str]): Its bold face.
        LABELS (ClassVar[Dict[Language, Dict[str, str]]]): Wording per language.
        HEADERS (ClassVar[Dict[Language, Tuple[str, ...]]]): Line-table column
            headings per language.
        PAGE_SIZE (ClassVar[Tuple[float, float]]): The page dimensions.
        MARGIN (ClassVar[float]): Margin on every side.
        LOGO_WIDTH (ClassVar[float]): Width the agency's logo is drawn at.
        LOGO_HEIGHT (ClassVar[float]): Height the agency's logo is drawn at.
        COLUMN_WIDTHS (ClassVar[Tuple[float, ...]]): Width of each line column.
        logger (Logger): Logger for rendering operations.

    Notes:
        - **Its own file, and its own class.** :class:`~service.utils.formatter.Formatter`
          is a single all-static class that writes worksheets; one class per
          file forbids adding to it, and every one of its layout methods takes a
          ``Worksheet``. What *is* reused are the pieces that produce text
          rather than cells — the trading name, the issuer's identity line, the
          rate and the duration — because those sentences must read identically
          on a quote and on the invoice that follows it.
        - **Instance methods, not static ones.** ``Formatter`` predates the
          house rule and is uniformly static; new code follows the rule.
        - Built on ``platypus`` rather than drawing on a canvas, so the visit
          table flows onto as many pages as it needs and repeats its header row.
          A yearly invoice can run to three hundred lines, and a fixed canvas
          would have printed the first forty and silently dropped the rest.
        - The obligations are French whatever language the reader chose. The
          catalogue translates the words; it does not translate the law, which
          is why the penalty and indemnity sentences say the same thing in both.
    """

    LABELS: ClassVar[Dict[Language, Dict[str, str]]] = {
        Language.FR: {
            "title": "FACTURE",
            "number": "Facture n°",
            "issued_on": "Date de facture",
            "due_on": "Échéance",
            "period": "Période d'exécution",
            "issued_by": "Émetteur",
            "billed_to": "Facturé à",
            "registration": "SIRET",
            "vat_number": "TVA",
            "share_capital": "Capital social",
            "sap": "Déclaration services à la personne n°",
            "sap_credit": (
                "Les sommes versées ouvrent droit au crédit d'impôt prévu à "
                "l'article 199 sexdecies du code général des impôts."
            ),
            "no_line": "Aucune prestation n'a été facturée sur cette période.",
            "untaxed": "Total HT",
            "tax_at": "TVA {rate}",
            "grand_total": "Total TTC",
            "legal_heading": "Conditions de règlement",
            "late_penalty": (
                "Tout retard de paiement entraîne des pénalités calculées au "
                "taux d'intérêt légal majoré de {multiplier} fois (code de "
                "commerce, art. L441-10)."
            ),
            "indemnity": (
                "Indemnité forfaitaire pour frais de recouvrement : "
                "{amount} € (code de commerce, art. D441-5)."
            ),
            "payment_details": "Coordonnées bancaires",
            "iban": "IBAN",
            "bic": "BIC",
            "delivered_by": "Intervenant",
            "not_planned": "—",
        },
        Language.EN: {
            "title": "INVOICE",
            "number": "Invoice no.",
            "issued_on": "Invoice date",
            "due_on": "Due date",
            "period": "Period of performance",
            "issued_by": "Issued by",
            "billed_to": "Billed to",
            "registration": "Reg. no.",
            "vat_number": "VAT",
            "share_capital": "Share capital",
            "sap": "Home-care service declaration no.",
            "sap_credit": (
                "Amounts paid qualify for the tax credit provided by article "
                "199 sexdecies of the French general tax code."
            ),
            "no_line": "No service was billed for this period.",
            "untaxed": "Total excl. VAT",
            "tax_at": "VAT {rate}",
            "grand_total": "Total incl. VAT",
            "legal_heading": "Payment terms",
            "late_penalty": (
                "Late payment carries interest at {multiplier} times the "
                "statutory rate (French Commercial Code, art. L441-10)."
            ),
            "indemnity": (
                "Fixed recovery charge: {amount} € (French Commercial Code, "
                "art. D441-5)."
            ),
            "payment_details": "Bank details",
            "iban": "IBAN",
            "bic": "BIC",
            "delivered_by": "Assistant",
            "not_planned": "—",
        },
    }

    HEADERS: ClassVar[Dict[Language, Tuple[str, ...]]] = {
        Language.FR: (
            "Date",
            "Prestation",
            "Intervenant",
            "Durée",
            "PU HT",
            "TVA",
            "Total HT",
        ),
        Language.EN: (
            "Date",
            "Service",
            "Assistant",
            "Hours",
            "Unit excl.",
            "VAT",
            "Total excl.",
        ),
    }

    FONT: ClassVar[str] = "InvoiceSans"
    BOLD_FONT: ClassVar[str] = "InvoiceSans-Bold"
    PAGE_SIZE: ClassVar[Tuple[float, float]] = A4
    MARGIN: ClassVar[float] = 15 * mm
    LOGO_WIDTH: ClassVar[float] = 45 * mm
    LOGO_HEIGHT: ClassVar[float] = 15 * mm
    COLUMN_WIDTHS: ClassVar[Tuple[float, ...]] = (
        20 * mm,
        45 * mm,
        30 * mm,
        18 * mm,
        22 * mm,
        16 * mm,
        24 * mm,
    )

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the renderer.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        self._register_fonts()
        self.styles = getSampleStyleSheet()
        # Every paragraph style, not only the ones used: a heading reached
        # through a parent would otherwise keep a face that is not embedded,
        # and the sample sheet also holds list styles, which carry no face at
        # all.
        for style in self.styles.byName.values():
            existing = getattr(style, "fontName", None)
            if existing is None:
                continue
            style.fontName = self.BOLD_FONT if "Bold" in existing else self.FONT
        self.right = ParagraphStyle(
            "InvoiceRight", parent=self.styles["BodyText"], alignment=TA_RIGHT
        )
        self.logger.debug("InvoiceRenderer created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _register_fonts(self) -> None:
        """Make the embedded typeface available, once per process.

        Notes:
            - **The built-in typefaces are not embedded, and an archival invoice
              must be.** Helvetica and its siblings are named in the file and
              resolved by whatever the reader happens to have, which is exactly
              what an archive format forbids: a document that renders
              differently in ten years is not a copy of what the customer was
              sent. A TrueType face is subset and written into the file itself.
            - The face ships **inside ReportLab**, so nothing new is added to
              the repository and no system font is depended on — a container
              with no fonts installed renders identically. It covers every
              accent French needs and the euro sign, which was checked rather
              than assumed.
            - Registration is global to the process and idempotent here, because
              a renderer is built per request in some paths and once in others.
        """
        if self.FONT in pdfmetrics.getRegisteredFontNames():
            return
        folder = Path(reportlab.__file__).parent / "fonts"
        for name, file_name in (
            (self.FONT, "Vera.ttf"),
            (self.BOLD_FONT, "VeraBd.ttf"),
        ):
            pdfmetrics.registerFont(TTFont(name, str(folder / file_name)))
        pdfmetrics.registerFontFamily(self.FONT, normal=self.FONT, bold=self.BOLD_FONT)
        self.logger.debug("Registered the embedded invoice typeface.")

    def _money(self, amount: Decimal) -> str:
        """Return an amount as it is printed.

        Args:
            amount (Decimal): The amount to render.

        Returns:
            str: The amount with a comma decimal separator and a euro sign.

        Notes:
            The comma is the decimal separator on a French document, and it is
            used whatever language the wording is in: the amount is in euros and
            is read by a French customer either way.
        """
        return f"{amount:,.2f} €".replace(",", " ").replace(".", ",")

    def _logo(self, logo: Optional[bytes]) -> Optional[Image]:
        """Return the agency's logo as a drawable, when there is one.

        Args:
            logo (Optional[bytes]): The image bytes, or ``None``.

        Returns:
            Optional[Image]: The drawable, or ``None`` when there is no usable
            logo.

        Notes:
            **Reports rather than raises.** A corrupt image must not stop an
            invoice going out: a document without its letterhead is still a
            legally complete invoice, and one that was never produced is a
            number burnt on nothing.
        """
        if not logo:
            self.logger.debug("No logo was supplied; the invoice prints without one.")
            return None
        try:
            return Image(BytesIO(logo), width=self.LOGO_WIDTH, height=self.LOGO_HEIGHT)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            self.logger.warning(
                "Could not draw the agency's logo (%s); the invoice prints without it.",
                exc,
            )
            return None

    def _header(
        self,
        bill: Bill,
        company: Company,
        labels: Dict[str, str],
        logo: Optional[bytes],
    ) -> List[Flowable]:
        """Return the title block and the issuer's identity.

        Args:
            bill (Bill): The invoice being rendered.
            company (Company): The agency issuing it.
            labels (Dict[str, str]): The wording for the language.
            logo (Optional[bytes]): The agency's logo, when it has one.

        Returns:
            List[Flowable]: The drawables, in printing order.

        Notes:
            The period of performance is printed beside the invoice date
            because French law requires it whenever the two differ — which, for
            a periodic invoice, they always do.
        """
        drawables: List[Flowable] = []
        drawn_logo = self._logo(logo)
        if drawn_logo is not None:
            drawables.append(drawn_logo)
        drawables.append(Paragraph(labels["title"], self.styles["Title"]))
        drawables.append(
            Paragraph(
                f"{labels['number']} {bill.number}<br/>"
                f"{labels['issued_on']} : {bill.issued_on:%d/%m/%Y}<br/>"
                f"{labels['due_on']} : {bill.due_on:%d/%m/%Y}<br/>"
                f"{labels['period']} : {bill.describe_period()}",
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
                "Invoice %s is being issued by an agency with no address, "
                "registration number or contact details; the document will not "
                "identify its issuer.",
                bill.number,
            )
        return drawables

    def _parties(self, bill: Bill, labels: Dict[str, str]) -> List[Flowable]:
        """Return the block naming who the invoice is addressed to.

        Args:
            bill (Bill): The invoice being rendered.
            labels (Dict[str, str]): The wording for the language.

        Returns:
            List[Flowable]: The drawables, in printing order.

        Notes:
            Read off the invoice's own copies of the name and address, never
            from a live customer record. A customer who moves must not change
            where last quarter's invoice says it was sent. No customer VAT
            number is printed: a private individual has none, and the mention is
            absent rather than blank.
        """
        return [
            Paragraph(
                f"<b>{labels['billed_to']}</b><br/>"
                f"{bill.customer_full_name}<br/>"
                f"{bill.customer_address.to_single_line()}",
                self.styles["BodyText"],
            )
        ]

    def _lines_table(self, bill: Bill, language: Language) -> Table:
        """Return the table of visits the invoice charges for.

        Args:
            bill (Bill): The invoice being rendered.
            language (Language): The language to write it in.

        Returns:
            Table: The table, with its header repeated on every page.

        Notes:
            - **Visits, never quotes.** Each row is a service on a day, with the
              assistant who delivered it and the hours they worked. No quote
              reference and no quote total appears anywhere on the document.
            - ``repeatRows=1`` is what makes a yearly invoice readable: the
              table flows across pages and the reader keeps their column
              headings.
            - A charge the planner never placed prints its sold date with a dash
              where the assistant would be. It is still billed — the work was
              agreed and delivered whether or not the solver saw it.
        """
        labels = self.LABELS[language]
        rows: List[List[str]] = [list(self.HEADERS[language])]
        for line in bill.sorted_lines():
            rows.append(
                [
                    f"{(line.day or line.service_date):%d/%m/%Y}",
                    line.name,
                    line.hca_full_name or labels["not_planned"],
                    Formatter.format_duration(line.duration_minutes, language),
                    self._money(line.hourly_rate_ht),
                    Formatter.format_rate(line.vat_rate),
                    self._money(line.total_ht),
                ]
            )
        if bill.is_empty():
            rows.append([labels["no_line"], "", "", "", "", "", ""])
        table = Table(rows, colWidths=list(self.COLUMN_WIDTHS), repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), self.BOLD_FONT),
                    ("FONTNAME", (0, 1), (-1, -1), self.FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        return table

    def _totals(self, bill: Bill, labels: Dict[str, str]) -> Table:
        """Return the totals block, with the tax broken down by rate.

        Args:
            bill (Bill): The invoice being rendered.
            labels (Dict[str, str]): The wording for the language.

        Returns:
            Table: The totals, right-aligned.

        Notes:
            **One row per VAT rate, never one merged figure.** A French invoice
            must state the tax at each rate it was charged at, and a home-care
            invoice routinely carries both — necessity assistance at 5.5%
            beside comfort work at 20%.
        """
        rows: List[List[str]] = [[labels["untaxed"], self._money(bill.total_ht)]]
        for rate, _, tax in bill.vat_by_rate():
            rows.append(
                [
                    labels["tax_at"].format(rate=Formatter.format_rate(rate)),
                    self._money(tax),
                ]
            )
        rows.append([labels["grand_total"], self._money(bill.total_ttc)])
        table = Table(rows, colWidths=[60 * mm, 35 * mm], hAlign="RIGHT")
        table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, -1), self.FONT),
                    ("FONTNAME", (0, -1), (-1, -1), self.BOLD_FONT),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        return table

    def _legal(
        self,
        company: Company,
        settings: BillingSettings,
        labels: Dict[str, str],
        language: Language,
    ) -> List[Flowable]:
        """Return the mandatory statements printed beneath the totals.

        Args:
            company (Company): The agency issuing the invoice.
            settings (BillingSettings): The terms it is issued under.
            labels (Dict[str, str]): The wording for the language.
            language (Language): The language to write it in.

        Returns:
            List[Flowable]: The drawables, in printing order.

        Notes:
            - The penalty and the recovery indemnity are **separate sentences**.
              The quote workbook folds them into one; on an invoice they are two
              distinct obligations and are stated as two.
            - The escompte is always mentioned, as "none" when none is offered:
              an invoice silent about it is itself non-conforming, which is why
              :meth:`~models.settings.billing_settings.BillingSettings.describe_terms`
              has no branch that omits it.
            - **The IBAN is printed in full**, and deliberately not through
              :meth:`~models.companies.company.Company.masked_iban`. That method
              exists so a manager reading the API does not see the whole
              account; a customer cannot pay into a masked one.
            - The *services à la personne* mention prints only when the agency
              has a declaration number. An agency that has not registered gets a
              document missing an optional line rather than one carrying a false
              declaration.
        """
        sentences: List[str] = [
            settings.describe_terms(language),
            labels["late_penalty"].format(multiplier=settings.late_penalty_multiplier),
            labels["indemnity"].format(
                amount=self._money(settings.recovery_indemnity_eur).replace(" €", "")
            ),
        ]
        if company.sap_declaration_number:
            sentences.append(
                f"{labels['sap']} {company.sap_declaration_number}. "
                f"{labels['sap_credit']}"
            )
        else:
            self.logger.warning(
                "Agency %s has no services-à-la-personne declaration number; "
                "the invoice prints without the tax-credit mention its "
                "customer would claim against.",
                company.name,
            )
        drawables: List[Flowable] = [
            Paragraph(f"<b>{labels['legal_heading']}</b>", self.styles["BodyText"]),
            Paragraph(" ".join(sentences), self.styles["BodyText"]),
        ]
        if company.iban:
            details = f"{labels['iban']} : {company.iban}"
            if company.bic:
                details = f"{details} · {labels['bic']} : {company.bic}"
            drawables.append(
                Paragraph(
                    f"<b>{labels['payment_details']}</b><br/>{details}",
                    self.styles["BodyText"],
                )
            )
        else:
            self.logger.warning(
                "Agency %s has no IBAN; the invoice tells the customer what "
                "they owe and not where to pay it.",
                company.name,
            )
        return drawables

    ############################
    # Publicly Exposed Methods #
    ############################

    def render(
        self,
        bill: Bill,
        customer: Customer,
        company: Company,
        settings: BillingSettings,
        language: Language = Language.FR,
        logo: Optional[bytes] = None,
    ) -> bytes:
        """Render one invoice as a PDF.

        Args:
            bill (Bill): The invoice to render.
            customer (Customer): The customer it is addressed to, for the log.
            company (Company): The agency issuing it.
            settings (BillingSettings): The terms it is issued under.
            language (Language): The language to write it in. Defaults to
                French.
            logo (Optional[bytes]): The agency's logo, when it has one.

        Returns:
            bytes: The rendered document.

        Raises:
            MTInvoiceRenderFailed: If the document could not be laid out.

        Notes:
            - The customer is taken for the log rather than for the page: the
              name and address printed are the invoice's own copies, so a record
              edited since cannot change what a reissued document says.
            - A failure here raises, unlike a missing logo, because the caller
              has already allocated an invoice number and must not store a
              record against a document that does not exist.
        """
        labels = self.LABELS[language]
        self.logger.debug(
            "Rendering invoice %s for customer %s (%d line(s), %s).",
            bill.number,
            customer.id,
            len(bill.lines),
            language.value,
        )
        buffer = BytesIO()
        drawables: List[Flowable] = []
        drawables.extend(self._header(bill, company, labels, logo))
        drawables.append(Spacer(1, 4 * mm))
        drawables.extend(self._parties(bill, labels))
        drawables.append(Spacer(1, 6 * mm))
        drawables.append(self._lines_table(bill, language))
        drawables.append(Spacer(1, 4 * mm))
        drawables.append(self._totals(bill, labels))
        drawables.append(Spacer(1, 6 * mm))
        drawables.extend(self._legal(company, settings, labels, language))
        try:
            document = SimpleDocTemplate(
                buffer,
                pagesize=self.PAGE_SIZE,
                topMargin=self.MARGIN,
                bottomMargin=self.MARGIN,
                leftMargin=self.MARGIN,
                rightMargin=self.MARGIN,
                title=f"{labels['title']} {bill.number}",
                author=Formatter.trading_name(company),
                initialFontName=self.FONT,
            )
            document.build(drawables)
        except Exception as exc:  # noqa: BLE001 - reported as a render failure
            self.logger.error("Could not render invoice %s: %s.", bill.number, exc)
            raise MTInvoiceRenderFailed(
                f"Could not render invoice {bill.number}: {exc}."
            ) from exc
        payload = buffer.getvalue()
        self.logger.info("Rendered invoice %s as %d bytes.", bill.number, len(payload))
        return payload
