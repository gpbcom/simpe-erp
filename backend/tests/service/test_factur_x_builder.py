from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Dict, List
from xml.etree import ElementTree

# Third-party imports
import pytest
from facturx import get_facturx_xml_from_pdf, get_level, xml_check_xsd
from lxml import etree
from pypdf import PdfReader

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_line import BillLine
from models.billing.bill_recipient import BillRecipient
from models.organisation.companies.company import Company
from models.enums import (
    BillingPeriodicity,
    Language,
    RecipientKind,
    ServiceCategory,
)
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.settings.billing_settings import BillingSettings
from service.integrations.utils.exceptions import (
    MTCiiNotSchemaValid,
    MTCiiSellerNotIdentified,
    MTCiiSplitNotRepresentable,
    MTFacturXAssemblyFailed,
)
from service.integrations.utils.factur_x import FacturXBuilder
from service.utils.invoice_renderer import InvoiceRenderer
from tests.annotations import ModelInput

ADDRESS = PostalAddress(
    street="1 rue des Lilas",
    postal_code="75011",
    city="Paris",
    country="France",
    latitude=48.85,
    longitude=2.35,
)
VALID_SIREN = "130025265"

#: The namespaces, so a test can ask for an element by the name the standard
#: gives it rather than by a path nobody can read.
NS = {prefix: uri for prefix, uri in FacturXBuilder.NAMESPACES}


def a_line(
    name: str = "Aide à la toilette",
    category: ServiceCategory = ServiceCategory.NECESSITY,
    rate: str = "25.00",
    total_ht: str = "50.00",
    served: date = date(2026, 3, 9),
) -> BillLine:
    """Build one charged visit.

    Args:
        name (str): What the service is.
        category (ServiceCategory): Its VAT category.
        rate (str): The hourly rate excluding tax.
        total_ht (str): The line total excluding tax.
        served (date): The day it was delivered.

    Returns:
        BillLine: The charge.
    """
    vat = (Decimal(total_ht) * category.vat_rate()).quantize(Decimal("0.01"))
    return BillLine(
        quote_line_id="line-1",
        name=name,
        service_category=category,
        service_date=served,
        duration_minutes=120,
        hourly_rate_ht=Decimal(rate),
        total_ht=Decimal(total_ht),
        vat_rate=category.vat_rate(),
        vat_amount=vat,
        total_ttc=Decimal(total_ht) + vat,
    )


def a_bill(lines: List[BillLine] | None = None, **overrides: ModelInput) -> Bill:
    """Build an invoice over the given charges.

    Args:
        lines (List[BillLine] | None): The charges, defaulting to one.
        **overrides: Fields to replace.

    Returns:
        Bill: The invoice.
    """
    charges = lines if lines is not None else [a_line()]
    payload: Dict[str, ModelInput] = {
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
        "customer_address": ADDRESS,
        "recipient": BillRecipient(name="Jeanne Vincent", address=ADDRESS),
        "lines": charges,
        "total_ht": sum((line.total_ht for line in charges), Decimal("0.00")),
        "total_vat": sum((line.vat_amount for line in charges), Decimal("0.00")),
        "total_ttc": sum((line.total_ttc for line in charges), Decimal("0.00")),
    }
    payload.update(overrides)
    return Bill(**payload)


def an_agency(**overrides: ModelInput) -> Company:
    """Build the agency issuing the invoice.

    Args:
        **overrides: Fields to replace.

    Returns:
        Company: The agency.
    """
    payload: Dict[str, ModelInput] = {
        "id": "company-1",
        "name": "Aide et Présence Paris",
        "legal_form": "SARL",
        "registration_number": "12345678900019",
        "vat_number": "FR12345678900",
        "iban": "FR7630006000011234567890189",
        "bic": "AGRIFRPP",
        "address": ADDRESS,
    }
    payload.update(overrides)
    return Company(**payload)


def parsed(payload: bytes) -> ElementTree.Element:
    """Return the built document as a tree.

    Args:
        payload (bytes): The XML.

    Returns:
        ElementTree.Element: Its root.
    """
    return ElementTree.fromstring(payload)


def text_at(root: ElementTree.Element, path: str) -> str | None:
    """Return the text of the first element matching a path.

    Args:
        root (ElementTree.Element): The document root.
        path (str): An ElementTree path using the standard prefixes.

    Returns:
        str | None: The text, or ``None`` when nothing matched.
    """
    found = root.find(path, NS)
    return found.text if found is not None else None


class TestTheStructuredInvoiceIsConforming:
    """Tests that the file we produce is the one the format describes."""

    def test_the_document_satisfies_the_official_schema(self) -> None:
        """**The gate, and it is a real one.**

        Notes:
            The element order in this format is fixed by the schema, and the
            order in the builder is the order of its calls — so moving two lines
            produces a file that reads correctly and no platform accepts. Run
            against the schema shipped with the reference implementation rather
            than against a golden file, which would only prove the output had
            not changed.
        """
        payload = FacturXBuilder().build(a_bill(), an_agency())

        xml_check_xsd(payload, flavor="factur-x", level="en16931")

    def test_the_schema_check_is_wired_into_the_builder(self) -> None:
        """**A file that fails the schema never leaves the builder.**

        Notes:
            The failure simulated is the one that actually happens: a refactor
            reorders two calls, and the schema fixes that order. Here the
            product name is emitted before the line identifier. Nothing about
            the resulting file *looks* wrong, and no platform accepts it — which
            is why the builder validates its own output rather than trusting
            that whoever moved the lines ran an end-to-end test.

            If this ever stops raising, the self-check has been removed and
            every other assertion in this file is worth much less.
        """

        class Reordered(FacturXBuilder):
            """A builder that emits one line's elements the wrong way round."""

            def _line(self, parent, position, line):  # noqa: ANN001, ANN202
                """Emit the product before the line identifier.

                Args:
                    parent: The transaction to append to.
                    position: The line's one-based position.
                    line: The charge.
                """
                item = self._child(parent, "ram", "IncludedSupplyChainTradeLineItem")
                product = self._child(item, "ram", "SpecifiedTradeProduct")
                self._child(product, "ram", "Name", line.name)
                document = self._child(item, "ram", "AssociatedDocumentLineDocument")
                self._child(document, "ram", "LineID", str(position))

        with pytest.raises(MTCiiNotSchemaValid):
            Reordered().build(a_bill(), an_agency())

    def test_the_declared_profile_is_the_european_rule_set(self) -> None:
        """The French rules are a profile of it, so the file names it."""
        root = parsed(FacturXBuilder().build(a_bill(), an_agency()))

        assert (
            text_at(
                root,
                "rsm:ExchangedDocumentContext/"
                "ram:GuidelineSpecifiedDocumentContextParameter/ram:ID",
            )
            == "urn:cen.eu:en16931:2017"
        )


class TestTheMandatoryMentions:
    """Tests for the terms a conforming invoice must carry."""

    def test_the_document_identifies_itself(self) -> None:
        """Number, type and date: the three that name the document."""
        root = parsed(FacturXBuilder().build(a_bill(), an_agency()))
        document = "rsm:ExchangedDocument/"

        assert text_at(root, f"{document}ram:ID") == "FA-2026-000001"
        assert text_at(root, f"{document}ram:TypeCode") == "380"
        assert (
            text_at(root, f"{document}ram:IssueDateTime/udt:DateTimeString")
            == "20260401"
        )

    def test_the_seller_carries_its_legal_identifiers(self) -> None:
        """**The SIREN is derived from the SIRET, never stored twice.**

        Notes:
            A second column would be free to disagree with the first the day
            somebody corrects one of them.
        """
        root = parsed(FacturXBuilder().build(a_bill(), an_agency()))
        seller = (
            "rsm:SupplyChainTradeTransaction/"
            "ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/"
        )

        assert text_at(root, f"{seller}ram:Name") == "Aide et Présence Paris"
        assert (
            text_at(root, f"{seller}ram:SpecifiedLegalOrganization/ram:ID")
            == "123456789"
        )
        assert (
            text_at(root, f"{seller}ram:SpecifiedTaxRegistration/ram:ID")
            == "FR12345678900"
        )
        assert text_at(root, f"{seller}ram:PostalTradeAddress/ram:CountryID") == "FR"

    def test_an_agency_with_no_vat_number_cannot_issue_one(self) -> None:
        """**Refused while the number can still be allocated.**

        Notes:
            The rules require the seller's VAT identifier wherever the tax
            breakdown names a rated category, which is every invoice this agency
            issues. Omitting it would produce a file the platform rejects,
            against an invoice number that cannot be reused.
        """
        with pytest.raises(MTCiiSellerNotIdentified):
            FacturXBuilder().build(a_bill(), an_agency(vat_number=None))

    def test_the_period_of_performance_is_stated(self) -> None:
        """Required whenever it differs from the invoice date, which is always."""
        root = parsed(FacturXBuilder().build(a_bill(), an_agency()))
        period = (
            "rsm:SupplyChainTradeTransaction/"
            "ram:ApplicableHeaderTradeSettlement/ram:BillingSpecifiedPeriod/"
        )

        assert text_at(root, f"{period}ram:StartDateTime/udt:DateTimeString") == (
            "20260301"
        )
        assert text_at(root, f"{period}ram:EndDateTime/udt:DateTimeString") == (
            "20260331"
        )

    def test_the_totals_are_the_bill_s_own(self) -> None:
        """Copied, never recomputed: an issued invoice may not move."""
        bill = a_bill()
        root = parsed(FacturXBuilder().build(bill, an_agency()))
        totals = (
            "rsm:SupplyChainTradeTransaction/"
            "ram:ApplicableHeaderTradeSettlement/"
            "ram:SpecifiedTradeSettlementHeaderMonetarySummation/"
        )

        assert text_at(root, f"{totals}ram:LineTotalAmount") == "50.00"
        assert text_at(root, f"{totals}ram:TaxTotalAmount") == "2.75"
        assert text_at(root, f"{totals}ram:GrandTotalAmount") == "52.75"
        assert text_at(root, f"{totals}ram:DuePayableAmount") == "52.75"
        assert bill.total_ttc == Decimal("52.75")

    def test_the_tax_is_broken_down_per_rate(self) -> None:
        """**Two rates on one invoice is the ordinary case here.**

        Notes:
            Assistance given for necessity is taxed at 5.5 % and comfort work at
            20 %, and a home-care invoice routinely carries both. A single
            merged figure would be unusable by the recipient's accounting.
        """
        bill = a_bill(
            [
                a_line(),
                a_line(
                    name="Ménage de confort",
                    category=ServiceCategory.COMFORT,
                    rate="30.00",
                    total_ht="60.00",
                    served=date(2026, 3, 12),
                ),
            ]
        )
        root = parsed(FacturXBuilder().build(bill, an_agency()))
        taxes = root.findall(
            "rsm:SupplyChainTradeTransaction/"
            "ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax",
            NS,
        )

        breakdown = {
            tax.find("ram:RateApplicablePercent", NS).text: (
                tax.find("ram:BasisAmount", NS).text,
                tax.find("ram:CalculatedAmount", NS).text,
            )
            for tax in taxes
        }
        assert breakdown == {
            "5.50": ("50.00", "2.75"),
            "20.00": ("60.00", "12.00"),
        }

    def test_the_rate_is_written_as_a_percentage(self) -> None:
        """**Stored as a fraction, printed as a percentage.**

        Notes:
            The one unit conversion in the file. The wrong way round declares
            0.055 % of tax on care sold at 5.5 % — two orders of magnitude out,
            and still a plausible-looking number.
        """
        root = parsed(FacturXBuilder().build(a_bill(), an_agency()))
        rate = text_at(
            root,
            "rsm:SupplyChainTradeTransaction/"
            "ram:IncludedSupplyChainTradeLineItem/"
            "ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/"
            "ram:RateApplicablePercent",
        )

        assert rate == "5.50"

    def test_every_line_carries_its_own_amounts(self) -> None:
        """Hours, unit price and total, in the units the agency sells in."""
        root = parsed(FacturXBuilder().build(a_bill(), an_agency()))
        item = "rsm:SupplyChainTradeTransaction/ram:IncludedSupplyChainTradeLineItem/"
        quantity = root.find(
            f"{item}ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", NS
        )

        assert text_at(root, f"{item}ram:SpecifiedTradeProduct/ram:Name") == (
            "Aide à la toilette"
        )
        assert quantity.text == "2.00"
        assert quantity.get("unitCode") == "HUR"
        assert (
            text_at(
                root,
                f"{item}ram:SpecifiedLineTradeAgreement/"
                f"ram:NetPriceProductTradePrice/ram:ChargeAmount",
            )
            == "25.00"
        )


class TestWhoIsBilledAndWhoWasServed:
    """Tests for the two parties an invoice names."""

    def test_a_household_pays_for_its_own_care(self) -> None:
        """The buyer and the ship-to party are the same, and both are stated."""
        root = parsed(FacturXBuilder().build(a_bill(), an_agency()))
        buyer = (
            "rsm:SupplyChainTradeTransaction/"
            "ram:ApplicableHeaderTradeAgreement/ram:BuyerTradeParty/ram:Name"
        )
        served = (
            "rsm:SupplyChainTradeTransaction/"
            "ram:ApplicableHeaderTradeDelivery/ram:ShipToTradeParty/ram:Name"
        )

        assert text_at(root, buyer) == "Jeanne Vincent"
        assert text_at(root, served) == "Jeanne Vincent"

    def test_a_funded_invoice_bills_one_party_and_names_another(self) -> None:
        """**The whole reason the two are separate fields.**

        Notes:
            A département receiving invoices for a hundred households can only
            use them if each says whose care it covers. The buyer is who pays;
            the ship-to party is where the work happened.
        """
        bill = a_bill(
            recipient=BillRecipient(
                kind=RecipientKind.PUBLIC,
                name="Conseil départemental de Paris",
                address=ADDRESS,
                siren=VALID_SIREN,
                service_code="APA",
            )
        )
        root = parsed(FacturXBuilder().build(bill, an_agency()))
        agreement = (
            "rsm:SupplyChainTradeTransaction/ram:ApplicableHeaderTradeAgreement/"
        )

        assert text_at(root, f"{agreement}ram:BuyerTradeParty/ram:Name") == (
            "Conseil départemental de Paris"
        )
        assert (
            text_at(
                root,
                f"{agreement}ram:BuyerTradeParty/ram:SpecifiedLegalOrganization/ram:ID",
            )
            == VALID_SIREN
        )
        assert (
            text_at(
                root,
                "rsm:SupplyChainTradeTransaction/"
                "ram:ApplicableHeaderTradeDelivery/ram:ShipToTradeParty/ram:Name",
            )
            == "Jeanne Vincent"
        )

    def test_a_split_invoice_is_refused_rather_than_misdeclared(self) -> None:
        """**A deliberate refusal, and the design chapter says why.**

        Notes:
            The rules tie the amount due to the total less what was prepaid, so
            one payer's share of two could only be expressed by calling the
            other party's part a prepayment — which it is not. Inventing that
            here would bury an unsettled modelling question in a file nobody
            reads until an auditor does.
        """
        bill = a_bill(
            recipient=BillRecipient(
                kind=RecipientKind.PUBLIC,
                name="Conseil départemental de Paris",
                address=ADDRESS,
                siren=VALID_SIREN,
                share_ttc="20.00",
            )
        )

        with pytest.raises(MTCiiSplitNotRepresentable):
            FacturXBuilder().build(bill, an_agency())


class TestWhatTheInvoiceMustNotSay:
    """Tests for what stays off the structured file."""

    def test_no_quote_is_named_anywhere(self) -> None:
        """**Requirement 9, carried into the structured half.**

        Notes:
            The originating quote line is stored on the charge so a disputed
            amount can be traced, and it is not part of the document. A
            recipient's system reading it would be reading an identifier the
            customer has never been shown.
        """
        payload = FacturXBuilder().build(a_bill(), an_agency())

        assert b"line-1" not in payload
        assert b"D-2648" not in payload


def a_customer() -> Customer:
    """Build the household the invoice is for.

    Returns:
        Customer: The customer.
    """
    return Customer(
        id="customer-1",
        first_name="Jeanne",
        last_name="Vincent",
        phone_number="+33612345678",
        email="jeanne.vincent@example.fr",
        address=ADDRESS,
    )


@pytest.fixture(scope="module")
def assembled() -> bytes:
    """Render and assemble one invoice, once for the whole module.

    Returns:
        bytes: The Factur-X document.

    Notes:
        Module-scoped because rendering a PDF and rewriting it with an
        attachment is the slowest thing in this file by an order of magnitude,
        and every test here asks a different question of the *same* document.
    """
    bill = a_bill()
    company = an_agency()
    pdf = InvoiceRenderer().render(
        bill=bill,
        customer=a_customer(),
        company=company,
        settings=BillingSettings(),
        language=Language.FR,
        logo=None,
    )
    xml = FacturXBuilder().build(bill, company)
    return FacturXBuilder().assemble(pdf=pdf, xml=xml, bill=bill, company=company)


class TestTheHybridDocument:
    """Tests for the one file both a human and a platform can read."""

    def test_it_is_a_pdf(self, assembled: bytes) -> None:
        """The half a customer opens."""
        assert assembled.startswith(b"%PDF-")

    def test_the_structured_invoice_travels_inside_it(self, assembled: bytes) -> None:
        """**The half a platform reads, and it must be recoverable.**

        Notes:
            Extracted with the reference implementation rather than by looking
            for the bytes: a file that merely *contains* the XML somewhere is
            not one a reader can find it in. This proves the attachment is
            declared where the format says it is.
        """
        name, extracted = get_facturx_xml_from_pdf(assembled)

        assert name == "factur-x.xml"
        assert b"CrossIndustryInvoice" in extracted

    def test_the_two_halves_state_the_same_invoice(self, assembled: bytes) -> None:
        """Built from one bill in one call, so they cannot disagree."""
        _name, extracted = get_facturx_xml_from_pdf(assembled)
        rebuilt = FacturXBuilder().build(a_bill(), an_agency())

        assert extracted == rebuilt

    def test_it_declares_the_profile_it_conforms_to(self, assembled: bytes) -> None:
        """A reader decides what to expect from this before parsing it."""
        _name, extracted = get_facturx_xml_from_pdf(assembled)

        assert get_level(etree.fromstring(extracted)) == "en16931"

    def test_every_font_is_embedded(self, assembled: bytes) -> None:
        """**An archival invoice may not depend on the reader's fonts.**

        Notes:
            A document naming a typeface it does not carry renders with whatever
            the reader substitutes, which in ten years may be nothing like what
            the customer was sent. This is also the prerequisite the archival
            profile is most often failed on, and the reason the renderer stopped
            using the built-in faces.
        """
        document = PdfReader(BytesIO(assembled))
        faces = {}
        for page in document.pages:
            fonts = (page.get("/Resources", {}) or {}).get("/Font", {}) or {}
            for entry in fonts.values():
                font = entry.get_object()
                descriptor = font.get("/FontDescriptor")
                faces[str(font.get("/BaseFont"))] = bool(
                    descriptor
                    and any(
                        key in descriptor
                        for key in ("/FontFile", "/FontFile2", "/FontFile3")
                    )
                )

        assert faces, "the document declares no font at all"
        unembedded = [name for name, ok in faces.items() if not ok]
        assert not unembedded, f"not embedded: {unembedded}"

    def test_the_document_is_titled_for_an_archive(self, assembled: bytes) -> None:
        """A file called "invoice.pdf" in an archive is one nobody finds."""
        metadata = PdfReader(BytesIO(assembled)).metadata

        assert "FA-2026-000001" in str(metadata.title)
        assert "Aide et Présence Paris" in str(metadata.author)


class TestWhenItCannotBeAssembled:
    """Tests for the refusal."""

    def test_something_that_is_not_a_pdf_is_refused(self) -> None:
        """**Refused rather than shipped as the plain page.**

        Notes:
            A PDF without its attachment and a Factur-X document look identical
            in a reader and are not remotely alike to a platform. Falling back
            silently is how an agency discovers a year later that nothing it
            sent was machine-readable.
        """
        bill = a_bill()
        company = an_agency()

        with pytest.raises(MTFacturXAssemblyFailed):
            FacturXBuilder().assemble(
                pdf=b"not a pdf at all",
                xml=FacturXBuilder().build(bill, company),
                bill=bill,
                company=company,
            )
