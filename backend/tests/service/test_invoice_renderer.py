from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from io import BytesIO
from typing import Any, Dict, List

# Third-party imports
from PIL import Image as PilImage
import pytest

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_line import BillLine
from models.companies.company import Company
from models.enums import BillingPeriodicity, Language, ServiceCategory
from models.people.customer import Customer
from models.settings.billing_settings import BillingSettings
from service.utils.exceptions import MTInvoiceRenderFailed
from service.utils.invoice_renderer import InvoiceRenderer


def a_png() -> bytes:
    """Return a small PNG standing in for the agency's logo.

    Returns:
        bytes: The image bytes.
    """
    buffer = BytesIO()
    PilImage.new("RGB", (240, 80), (20, 90, 160)).save(buffer, "PNG")
    return buffer.getvalue()


def a_charge(
    service_date: date = date(2026, 3, 9),
    name: str = "Aide à la toilette",
    hca: str | None = "Amina Benali",
    category: ServiceCategory = ServiceCategory.NECESSITY,
    total_ht: str = "63.82",
    vat_rate: str = "0.055",
    vat_amount: str = "3.51",
) -> BillLine:
    """Build one charged visit.

    Args:
        service_date (date): The day the service was sold for.
        name (str): What the service is.
        hca (str | None): Who delivered it, or ``None`` when unplanned.
        category (ServiceCategory): What kind of care it is.
        total_ht (str): The line total excluding tax.
        vat_rate (str): The rate the tax was charged at.
        vat_amount (str): The tax on the line.

    Returns:
        BillLine: The charge.
    """
    delivered = hca is not None
    return BillLine(
        quote_line_id="quote-line-1",
        name=name,
        service_category=category,
        service_date=service_date,
        day=service_date if delivered else None,
        start_time=time(9, 0) if delivered else None,
        end_time=time(11, 0) if delivered else None,
        hca_full_name=hca,
        duration_minutes=120,
        hourly_rate_ht=Decimal("31.91"),
        total_ht=Decimal(total_ht),
        vat_rate=Decimal(vat_rate),
        vat_amount=Decimal(vat_amount),
        total_ttc=Decimal(total_ht) + Decimal(vat_amount),
    )


def a_bill(**overrides: Any) -> Bill:
    """Build a March invoice.

    Args:
        **overrides: Fields to replace on the default invoice.

    Returns:
        Bill: The invoice.
    """
    lines: List[BillLine] = overrides.pop("lines", [a_charge()])
    payload: Dict[str, Any] = {
        "company_id": "company-1",
        "customer_id": "customer-1",
        "number": "FA-2026-000001",
        "sequence": 1,
        "sequence_year": 2026,
        "periodicity": BillingPeriodicity.MONTHLY,
        "period_start": date(2026, 3, 1),
        "period_end": date(2026, 3, 31),
        "issued_on": date(2026, 4, 1),
        "due_on": date(2026, 5, 1),
        "customer_full_name": "Jeanne Vincent",
        "customer_address": {
            "street": "1 rue des Lilas",
            "postal_code": "75011",
            "city": "Paris",
            "country": "France",
        },
        "lines": lines,
        "total_ht": sum((line.total_ht for line in lines), Decimal("0.00")),
        "total_vat": sum((line.vat_amount for line in lines), Decimal("0.00")),
        "total_ttc": sum((line.total_ttc for line in lines), Decimal("0.00")),
    }
    payload.update(overrides)
    return Bill(**payload)


def an_agency(**overrides: Any) -> Company:
    """Build an agency with a complete legal identity.

    Args:
        **overrides: Fields to replace on the default agency.

    Returns:
        Company: The agency.
    """
    payload: Dict[str, Any] = {
        "name": "Aide et Présence Paris",
        "legal_form": "SARL",
        "registration_number": "12345678901234",
        "rcs_number": "RCS Paris B 123 456 789",
        "vat_number": "FR12345678901",
        "share_capital": Decimal("10000"),
        "phone_number": "+33145678901",
        "iban": "FR7630006000011234567890189",
        "bic": "AGRIFRPP",
        "sap_declaration_number": "SAP/2026/0042",
        "address": {
            "street": "5 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "country": "France",
        },
    }
    payload.update(overrides)
    return Company(**payload)


def a_customer() -> Customer:
    """Build the customer an invoice is addressed to.

    Returns:
        Customer: The customer.
    """
    return Customer(
        first_name="Jeanne",
        last_name="Vincent",
        phone_number="+33612345678",
        email="jeanne.vincent@example.com",
        address={
            "street": "1 rue des Lilas",
            "postal_code": "75011",
            "city": "Paris",
        },
    )


def table_text(renderer: InvoiceRenderer, bill: Bill, language: Language) -> str:
    """Return the line table's cell data as one searchable string.

    Args:
        renderer (InvoiceRenderer): The renderer under test.
        bill (Bill): The invoice being rendered.
        language (Language): The language to build it in.

    Returns:
        str: Every cell, joined.

    Notes:
        The tests assert on the data the renderer *builds*, not on text pulled
        back out of a PDF. Extracting text would mean adding a PDF-reading
        dependency to prove something the layout already knows, and would break
        on a line wrap that changed nothing about the content.
    """
    table = renderer._lines_table(bill, language)
    return " | ".join(
        str(cell)
        for row in table._cellvalues
        for cell in row  # noqa: SLF001
    )


def legal_text(
    renderer: InvoiceRenderer,
    company: Company,
    settings: BillingSettings,
    language: Language = Language.FR,
) -> str:
    """Return the mandatory statements as one searchable string.

    Args:
        renderer (InvoiceRenderer): The renderer under test.
        company (Company): The agency issuing the invoice.
        settings (BillingSettings): The terms it is issued under.
        language (Language): The language to build it in.

    Returns:
        str: The rendered sentences, joined.
    """
    labels = InvoiceRenderer.LABELS[language]
    drawables = renderer._legal(company, settings, labels, language)  # noqa: SLF001
    return " ".join(str(getattr(item, "text", "")) for item in drawables)


@pytest.fixture
def renderer() -> InvoiceRenderer:
    """Return a renderer.

    Returns:
        InvoiceRenderer: The renderer under test.
    """
    return InvoiceRenderer()


class TestTheDocumentIsProduced:
    """Tests that a renderable invoice actually renders."""

    @pytest.mark.parametrize("language", list(Language))
    def test_the_payload_is_a_pdf(
        self, renderer: InvoiceRenderer, language: Language
    ) -> None:
        """Both languages produce a real document.

        Args:
            language (Language): The language rendered.
        """
        payload = renderer.render(
            a_bill(), a_customer(), an_agency(), BillingSettings(), language
        )

        assert payload.startswith(b"%PDF-")
        assert len(payload) > 1000

    def test_an_empty_period_still_produces_a_document(
        self, renderer: InvoiceRenderer
    ) -> None:
        """A renderer must not be the thing that decides not to bill.

        Notes:
            Whether an empty period is worth an invoice is the service's
            decision — it declines to issue one — but a renderer that crashed
            on an empty list would turn that judgement into a stack trace.
        """
        empty = a_bill(
            lines=[],
            total_ht=Decimal("0.00"),
            total_vat=Decimal("0.00"),
            total_ttc=Decimal("0.00"),
        )

        assert renderer.render(
            empty, a_customer(), an_agency(), BillingSettings()
        ).startswith(b"%PDF-")

    def test_a_long_invoice_paginates(self, renderer: InvoiceRenderer) -> None:
        """A yearly invoice runs to hundreds of lines.

        Notes:
            This is why the table is a flowing ``platypus`` one with
            ``repeatRows=1`` rather than something drawn on a canvas: a fixed
            canvas would have printed the first forty rows and silently dropped
            the rest, on a document a customer is asked to pay.
        """
        many = [
            a_charge(service_date=date(2026, 3, 1 + index % 31)) for index in range(200)
        ]
        long_bill = a_bill(lines=many, period_end=date(2026, 3, 31))

        payload = renderer.render(
            long_bill, a_customer(), an_agency(), BillingSettings()
        )
        assert payload.count(b"/Type /Page") > 1

    def test_a_failure_to_lay_out_is_raised(self, renderer: InvoiceRenderer) -> None:
        """A number is already allocated, so a silent failure is a gap.

        Notes:
            Unlike a missing logo, which is reported and skipped. A document
            without its letterhead is still an invoice; one that does not exist
            is a burnt number the series cannot explain.
        """
        renderer.PAGE_SIZE = (1.0, 1.0)

        with pytest.raises(MTInvoiceRenderFailed):
            renderer.render(a_bill(), a_customer(), an_agency(), BillingSettings())


class TestTheLogoIsOptional:
    """Tests for the letterhead, which never stops an invoice going out."""

    def test_a_usable_logo_is_drawn(self, renderer: InvoiceRenderer) -> None:
        """The agency's own mark, when it has one."""
        assert renderer._logo(a_png()) is not None  # noqa: SLF001

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(None, id="no logo at all"),
            pytest.param(b"", id="an empty one"),
            pytest.param(b"not an image", id="a corrupt one"),
        ],
    )
    def test_an_unusable_logo_is_dropped_not_raised(
        self, renderer: InvoiceRenderer, payload: bytes | None
    ) -> None:
        """**Reports rather than raises.**

        Args:
            payload (bytes | None): The unusable logo.

        Notes:
            An invoice that could not be issued because a decoration was
            corrupt would be a far worse outcome than one that goes out plain.
        """
        assert renderer._logo(payload) is None  # noqa: SLF001

    def test_the_document_renders_without_a_logo(
        self, renderer: InvoiceRenderer
    ) -> None:
        """And the whole document still comes out."""
        assert renderer.render(
            a_bill(),
            a_customer(),
            an_agency(logo_url=None),
            BillingSettings(),
            Language.FR,
            logo=b"not an image",
        ).startswith(b"%PDF-")


class TestTheInvoiceListsVisits:
    """Tests for requirement 9: interventions, never quotes."""

    def test_each_row_names_a_visit(self, renderer: InvoiceRenderer) -> None:
        """Date, service, assistant and hours — what was done, not what was sold."""
        text = table_text(renderer, a_bill(), Language.FR)

        assert "09/03/2026" in text
        assert "Aide à la toilette" in text
        assert "Amina Benali" in text
        assert "2 h 00" in text

    def test_no_quote_reference_reaches_the_page(
        self, renderer: InvoiceRenderer
    ) -> None:
        """**The whole of requirement 9, made testable.**

        Notes:
            ``quote_line_id`` is stored on every charge so a disputed line can
            be traced in a support conversation. It must never be printed: a
            customer's question is what was done for them, and a document
            answering "quote line ql-1" answers a different one.
        """
        text = table_text(renderer, a_bill(), Language.FR)

        assert "quote-line-1" not in text
        assert "quote" not in text.lower()

    def test_an_unplanned_service_prints_a_dash_and_is_still_billed(
        self, renderer: InvoiceRenderer
    ) -> None:
        """Work delivered off the plan is not silently forgiven.

        Notes:
            A charge with no matching intervention keeps its sold date and
            prints a dash where the assistant would be. Dropping it would mean
            the agency never asking for money it earned.
        """
        unplanned = a_bill(lines=[a_charge(name="Courses", hca=None)])
        text = table_text(renderer, unplanned, Language.FR)

        assert "Courses" in text
        assert "—" in text

    def test_the_rows_are_in_the_order_the_month_happened(
        self, renderer: InvoiceRenderer
    ) -> None:
        """A customer reads an invoice as a diary."""
        out_of_order = a_bill(
            lines=[
                a_charge(service_date=date(2026, 3, 20), name="Courses"),
                a_charge(service_date=date(2026, 3, 2), name="Toilette"),
            ]
        )
        text = table_text(renderer, out_of_order, Language.FR)

        assert text.index("Toilette") < text.index("Courses")

    def test_an_empty_period_says_so_rather_than_printing_nothing(
        self, renderer: InvoiceRenderer
    ) -> None:
        """A blank table looks like a rendering fault."""
        empty = a_bill(
            lines=[],
            total_ht=Decimal("0.00"),
            total_vat=Decimal("0.00"),
            total_ttc=Decimal("0.00"),
        )

        assert "Aucune prestation" in table_text(renderer, empty, Language.FR)


class TestTheMandatoryMentions:
    """Tests for what French law requires the document to say."""

    def test_the_tax_is_broken_down_by_rate(self, renderer: InvoiceRenderer) -> None:
        """**One row per rate, never one merged figure.**

        Notes:
            A home-care invoice routinely carries both — necessity assistance
            at 5.5% beside comfort work at 20% — and stating a single "VAT"
            total would make the document non-conforming.
        """
        mixed = a_bill(
            lines=[
                a_charge(vat_rate="0.055", vat_amount="3.51"),
                a_charge(
                    name="Courses",
                    category=ServiceCategory.COMFORT,
                    vat_rate="0.20",
                    vat_amount="12.76",
                ),
            ]
        )
        totals = renderer._totals(  # noqa: SLF001
            mixed, InvoiceRenderer.LABELS[Language.FR]
        )
        text = " ".join(
            str(cell)
            for row in totals._cellvalues
            for cell in row  # noqa: SLF001
        )

        assert "TVA 5.5%" in text
        assert "TVA 20%" in text
        assert "3,51 €" in text
        assert "12,76 €" in text
        assert "Total TTC" in text

    def test_the_penalty_and_the_indemnity_are_separate_sentences(
        self, renderer: InvoiceRenderer
    ) -> None:
        """**Two obligations, stated as two.**

        Notes:
            The quote workbook folds the €40 recovery charge into the
            late-payment sentence. On an invoice they are distinct legal
            mentions — art. L441-10 and art. D441-5 — and merging them omits
            one of them.
        """
        text = legal_text(renderer, an_agency(), BillingSettings())

        assert "L441-10" in text
        assert "D441-5" in text
        assert "40,00 €" in text

    def test_the_penalty_multiplier_is_the_configured_one(
        self, renderer: InvoiceRenderer
    ) -> None:
        """A rule a manager set is a rule the document states."""
        text = legal_text(
            renderer, an_agency(), BillingSettings(late_penalty_multiplier=5)
        )

        assert "majoré de 5 fois" in text

    @pytest.mark.parametrize(
        ("offered", "expected"),
        [
            pytest.param(False, "néant", id="no discount"),
            pytest.param(True, "accordé", id="a discount"),
        ],
    )
    def test_the_escompte_is_always_mentioned(
        self, renderer: InvoiceRenderer, offered: bool, expected: str
    ) -> None:
        """Silence about the early-settlement discount is non-conformity.

        Args:
            offered (bool): Whether a discount is offered.
            expected (str): The word the document must carry.
        """
        text = legal_text(
            renderer, an_agency(), BillingSettings(escompte_offered=offered)
        )

        assert "Escompte" in text
        assert expected in text

    def test_the_iban_is_printed_in_full(self, renderer: InvoiceRenderer) -> None:
        """**Never the masked form.**

        Notes:
            :meth:`~models.companies.company.Company.masked_iban` exists so a
            manager reading the API does not see a whole account number. A
            customer cannot pay into a masked one, so the document prints it
            whole — which is what an IBAN is for.
        """
        agency = an_agency()
        text = legal_text(renderer, agency, BillingSettings())

        assert agency.iban is not None
        assert agency.iban in text
        assert agency.masked_iban() not in text
        assert "AGRIFRPP" in text

    def test_the_sap_declaration_is_printed_when_there_is_one(
        self, renderer: InvoiceRenderer
    ) -> None:
        """The line a customer claims their tax credit against."""
        text = legal_text(renderer, an_agency(), BillingSettings())

        assert "SAP/2026/0042" in text
        assert "199 sexdecies" in text

    def test_an_unregistered_agency_prints_without_the_mention(
        self, renderer: InvoiceRenderer
    ) -> None:
        """A missing line beats a false declaration.

        Notes:
            There is no safe value to invent for a declaration number, so an
            agency that has not registered gets a document without the mention
            rather than one carrying something made up.
        """
        text = legal_text(
            renderer, an_agency(sap_declaration_number=None), BillingSettings()
        )

        assert "199 sexdecies" not in text
        assert "L441-10" in text

    def test_an_agency_with_no_iban_still_renders(
        self, renderer: InvoiceRenderer
    ) -> None:
        """It tells the customer what they owe, and warns about the rest."""
        text = legal_text(renderer, an_agency(iban=None), BillingSettings())

        assert "IBAN" not in text
        assert "L441-10" in text

    def test_the_obligations_are_french_in_english_too(
        self, renderer: InvoiceRenderer
    ) -> None:
        """The catalogue translates the words, not the law.

        Notes:
            The same sentence a French reader gets, in English: an agency whose
            customer prefers English still owes exactly the same statements.
        """
        text = legal_text(renderer, an_agency(), BillingSettings(), Language.EN)

        assert "L441-10" in text
        assert "D441-5" in text
        assert "199 sexdecies" in text


class TestTheAmountsAreFrench:
    """Tests for how money is written on the page."""

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            pytest.param(Decimal("63.82"), "63,82 €", id="a comma separator"),
            pytest.param(Decimal("1234.50"), "1 234,50 €", id="a space for thousands"),
            pytest.param(Decimal("0.00"), "0,00 €", id="zero"),
        ],
    )
    def test_amounts_use_the_french_convention(
        self, renderer: InvoiceRenderer, amount: Decimal, expected: str
    ) -> None:
        """A comma decimal separator, whatever language the wording is in.

        Args:
            amount (Decimal): The amount rendered.
            expected (str): How it must appear.

        Notes:
            The amount is in euros and is read by a French customer either way,
            so the number formatting does not follow the language the sentences
            are written in.
        """
        assert renderer._money(amount) == expected  # noqa: SLF001
