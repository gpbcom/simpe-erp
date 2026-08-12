from __future__ import annotations

# Standard library imports
from decimal import Decimal
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple
from xml.etree import ElementTree

# Third-party imports
from facturx import generate_from_binary, xml_check_xsd

# First-party imports
from models.billing.bill import Bill
from models.billing.bill_line import BillLine
from models.organisation.companies.company import Company
from models.enums import Language
from models.geo.postal_address import PostalAddress
from service.integrations.utils.exceptions import (
    MTCiiNotSchemaValid,
    MTCiiRecipientNotIdentified,
    MTCiiSellerNotIdentified,
    MTCiiSplitNotRepresentable,
    MTFacturXAssemblyFailed,
)


class FacturXBuilder:
    """Writes an invoice as the file a platform reads, inside the one a human does.

    Attributes:
        NAMESPACES (ClassVar[...]): The four CII namespaces and their prefixes.
        SPECIFICATION (ClassVar[str]): The rule set the structured file declares.
        TYPE_CODE (ClassVar[str]): The document type — a commercial invoice.
        DATE_FORMAT_CODE (ClassVar[str]): The date qualifier, ``YYYYMMDD``.
        HOUR_UNIT (ClassVar[str]): The unit hours are billed in.
        VAT (ClassVar[str]): The tax type code.
        STANDARD_CATEGORY (ClassVar[str]): The VAT category code used here.
        CREDIT_TRANSFER (ClassVar[str]): The payment-means code for a transfer.
        COUNTRY_CODES (ClassVar[Dict[str, str]]): Country names to ISO codes.
        FLAVOR (ClassVar[str]): The hybrid format produced.
        LEVEL (ClassVar[str]): The profile the attachment conforms to.
        RELATIONSHIP (ClassVar[str]): How the attachment relates to the page.
        logger (Logger): Logger for build and assembly operations.

    Notes:
        - **One class because it is one document.** A Factur-X invoice is a PDF
          carrying its own CII XML: the customer opens a page they recognise and
          a platform reads the structured data out of the same file. Splitting
          the writing of the XML from its attachment made two objects that were
          only ever used together and could only ever disagree.
        - **This is the invoice, and the PDF is a picture of it.** Both halves
          are built from one :class:`~models.billing.bill.Bill` so they cannot
          state different totals — the alternative, deriving the XML from the
          PDF or from a second query, is exactly how they come to.
        - **Nothing is computed here.** Every amount is copied from the bill,
          which copied it from the quote line that sold it. A builder that
          re-derived a total would be a second pricing path, and the one thing
          an invoice may never do is move after it is issued.
        - Written with the standard library rather than a template. The element
          *order* is part of the schema, so a template would put the constraint
          in a file no test can see; here the order is the order of the calls,
          and the conformance test is a real validator rather than a diff.
        - **The library owns the XMP metadata, deliberately.** The attachment
          has to be declared in a packet naming the Factur-X extension schema
          and the conformance level, and a subtly wrong packet is a file that
          opens perfectly and is rejected on receipt. That block is a compliance
          artifact rather than something to hand-roll.
        - The French rules are a profile of a European standard, so the file
          declares ``urn:cen.eu:en16931:2017`` and is checked against that rule
          set. What the reform adds on top — routing, lifecycle, transmission —
          is not in this file at all; it belongs to the platform.
        - What this does **not** do is make the document archival-grade PDF/A-3.
          That additionally needs an output intent carrying an ICC profile,
          which is a binary asset this repository does not ship. The gap is
          recorded in the design chapter; every other Factur-X requirement is
          met.
    """

    NAMESPACES: ClassVar[Tuple[Tuple[str, str], ...]] = (
        (
            "rsm",
            "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
        ),
        (
            "ram",
            "urn:un:unece:uncefact:data:standard:"
            "ReusableAggregateBusinessInformationEntity:100",
        ),
        (
            "udt",
            "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
        ),
        (
            "qdt",
            "urn:un:unece:uncefact:data:standard:QualifiedDataType:100",
        ),
    )
    SPECIFICATION: ClassVar[str] = "urn:cen.eu:en16931:2017"
    TYPE_CODE: ClassVar[str] = "380"
    DATE_FORMAT_CODE: ClassVar[str] = "102"
    HOUR_UNIT: ClassVar[str] = "HUR"
    VAT: ClassVar[str] = "VAT"
    STANDARD_CATEGORY: ClassVar[str] = "S"
    CREDIT_TRANSFER: ClassVar[str] = "30"
    COUNTRY_CODES: ClassVar[Dict[str, str]] = {
        "france": "FR",
        "belgique": "BE",
        "belgium": "BE",
        "suisse": "CH",
        "switzerland": "CH",
        "luxembourg": "LU",
        "monaco": "MC",
    }

    FLAVOR: ClassVar[str] = "factur-x"
    LEVEL: ClassVar[str] = "en16931"
    RELATIONSHIP: ClassVar[str] = "data"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the builder.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("FacturXBuilder created.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _qualified(self, prefix: str, name: str) -> str:
        """Return an element name in Clark notation.

        Args:
            prefix (str): The namespace prefix, ``rsm``, ``ram`` or ``udt``.
            name (str): The local element name.

        Returns:
            str: ``{namespace}name``, which is what ElementTree wants.
        """
        return f"{{{dict(self.NAMESPACES)[prefix]}}}{name}"

    def _child(
        self,
        parent: ElementTree.Element,
        prefix: str,
        name: str,
        text: Optional[str] = None,
    ) -> ElementTree.Element:
        """Append one element, optionally carrying a value.

        Args:
            parent (ElementTree.Element): The element to append to.
            prefix (str): The namespace prefix.
            name (str): The local element name.
            text (Optional[str]): The value, when the element carries one.

        Returns:
            ElementTree.Element: The appended element, for nesting into.
        """
        element = ElementTree.SubElement(parent, self._qualified(prefix, name))
        if text is not None:
            element.text = text
        return element

    def _money(self, amount: Decimal) -> str:
        """Return an amount as the format writes it.

        Args:
            amount (Decimal): The amount.

        Returns:
            str: The amount to two decimal places.

        Notes:
            Two places always, including on a whole number of euros. The rule
            set caps the decimals rather than fixing them, but a mix of ``40``
            and ``40.00`` down one document is the kind of thing a strict reader
            on the other side rejects and nobody can reproduce locally.
        """
        return f"{amount:.2f}"

    def _percentage(self, rate: Decimal) -> str:
        """Return a VAT rate as a percentage.

        Args:
            rate (Decimal): The rate as stored, ``0.055`` for 5.5 %.

        Returns:
            str: The rate as a percentage to two decimal places.

        Notes:
            Stored as a fraction and printed as a percentage, which is the one
            unit conversion in this file. Getting it the wrong way round would
            declare 0.055 % of tax on care sold at 5.5 % — an error of two
            orders of magnitude that still looks like a plausible number.
        """
        return f"{rate * 100:.2f}"

    def _date(
        self, parent: ElementTree.Element, prefix: str, name: str, value: str
    ) -> None:
        """Append a qualified date element.

        Args:
            parent (ElementTree.Element): The element to append to.
            prefix (str): The namespace prefix of the wrapper.
            name (str): The local name of the wrapper.
            value (str): The date, already in ``YYYYMMDD`` form.

        Notes:
            Every date in the format is a wrapper around a string that names its
            own format code. Building it here once is what stops one of the five
            dates on an invoice being written a different way.
        """
        wrapper = self._child(parent, prefix, name)
        element = self._child(wrapper, "udt", "DateTimeString", value)
        element.set("format", self.DATE_FORMAT_CODE)

    def _address(self, parent: ElementTree.Element, address: PostalAddress) -> None:  # noqa: E501
        """Append a postal address in the order the schema wants it.

        Args:
            parent (ElementTree.Element): The trade party to append to.
            address (PostalAddress): The address.

        Notes:
            The country is a two-letter code and the model stores a country
            *name*, because the name is what gets printed and what the geocoder
            was given. France is the only country this agency delivers in, so
            the mapping is a lookup with a documented fallback rather than a
            table nobody maintains — an unknown name yields ``FR`` and a
            warning, which is wrong in a way somebody can see rather than an
            empty element the schema refuses.
        """
        block = self._child(parent, "ram", "PostalTradeAddress")
        self._child(block, "ram", "PostcodeCode", address.postal_code)
        self._child(block, "ram", "LineOne", address.street)
        self._child(block, "ram", "CityName", address.city)
        code = self.COUNTRY_CODES.get(address.country.strip().lower())
        if code is None:
            self.logger.warning(
                "No ISO country code is known for %r; the structured invoice "
                "will declare FR.",
                address.country,
            )
            code = "FR"
        self._child(block, "ram", "CountryID", code)

    def _seller(self, parent: ElementTree.Element, company: Company) -> None:
        """Append the agency issuing the invoice.

        Args:
            parent (ElementTree.Element): The trade agreement to append to.
            company (Company): The agency.

        Raises:
            MTCiiSellerNotIdentified: If the agency has no VAT number.

        Notes:
            The VAT number is refused as missing rather than left out. The
            European rules require it wherever a tax breakdown names a rated
            category, which is every invoice this agency issues, so a file
            without it is one the platform will reject — and it is better to
            fail while the number can still be allocated than after.
        """
        if not company.vat_number:
            self.logger.error(
                "Agency %s has no VAT number; no conforming structured "
                "invoice can be built for it.",
                company.name,
            )
            raise MTCiiSellerNotIdentified(
                f"Agency {company.name!r} has no intra-community VAT number, "
                f"which a structured invoice charging VAT must carry."
            )
        party = self._child(parent, "ram", "SellerTradeParty")
        self._child(party, "ram", "Name", company.name)
        siren = company.siren()
        if siren:
            legal = self._child(party, "ram", "SpecifiedLegalOrganization")
            identifier = self._child(legal, "ram", "ID", siren)
            identifier.set("schemeID", "0002")
        else:
            self.logger.warning(
                "Agency %s has no readable SIREN; the structured invoice will "
                "name it without a legal registration.",
                company.name,
            )
        self._address(party, company.address)
        registration = self._child(party, "ram", "SpecifiedTaxRegistration")
        vat = self._child(registration, "ram", "ID", company.vat_number)
        vat.set("schemeID", "VA")

    def _buyer(self, parent: ElementTree.Element, bill: Bill) -> None:
        """Append the party that owes the money.

        Args:
            parent (ElementTree.Element): The trade agreement to append to.
            bill (Bill): The invoice being written.

        Raises:
            MTCiiRecipientNotIdentified: If a professional carries no SIREN.

        Notes:
            **Not the customer.** The buyer is whoever is being asked to pay,
            which on a funded arrangement is a département or a mutuelle. The
            household appears further down as the party the care was delivered
            to, which is a different element and a different question.
        """
        recipient = bill.recipient
        if recipient.kind.requires_legal_identifier() and not recipient.siren:
            self.logger.error(
                "Recipient %s of bill %s has no SIREN and cannot be routed to.",
                recipient.name,
                bill.number,
            )
            raise MTCiiRecipientNotIdentified(
                f"Recipient {recipient.name!r} is a "
                f"{recipient.kind.value} and carries no SIREN, so the invoice "
                f"cannot be delivered."
            )
        party = self._child(parent, "ram", "BuyerTradeParty")
        self._child(party, "ram", "Name", recipient.name)
        if recipient.siren:
            legal = self._child(party, "ram", "SpecifiedLegalOrganization")
            identifier = self._child(legal, "ram", "ID", recipient.siren)
            identifier.set("schemeID", "0002")
        self._address(party, recipient.address)
        if recipient.vat_number:
            registration = self._child(party, "ram", "SpecifiedTaxRegistration")
            vat = self._child(registration, "ram", "ID", recipient.vat_number)
            vat.set("schemeID", "VA")

    def _line(self, parent: ElementTree.Element, position: int, line: BillLine) -> None:  # noqa: E501
        """Append one charged visit.

        Args:
            parent (ElementTree.Element): The transaction to append to.
            position (int): The line's one-based position.
            line (BillLine): The charge.

        Notes:
            - Billed in **hours**, because that is what the agency sells and
              what the customer recognises on the page beside it. The quantity
              is the visit's duration, and the unit price is the hourly rate the
              quote was priced at.
            - The line total is **copied, not multiplied out**. Rate times hours
              can land a cent away from the amount the customer was quoted, and
              the quoted amount is the one that is owed.
        """
        item = self._child(parent, "ram", "IncludedSupplyChainTradeLineItem")
        document = self._child(item, "ram", "AssociatedDocumentLineDocument")
        self._child(document, "ram", "LineID", str(position))
        product = self._child(item, "ram", "SpecifiedTradeProduct")
        self._child(product, "ram", "Name", line.name)

        agreement = self._child(item, "ram", "SpecifiedLineTradeAgreement")
        price = self._child(agreement, "ram", "NetPriceProductTradePrice")
        self._child(price, "ram", "ChargeAmount", self._money(line.hourly_rate_ht))

        delivery = self._child(item, "ram", "SpecifiedLineTradeDelivery")
        quantity = self._child(
            delivery, "ram", "BilledQuantity", f"{line.duration_hours():.2f}"
        )
        quantity.set("unitCode", self.HOUR_UNIT)

        settlement = self._child(item, "ram", "SpecifiedLineTradeSettlement")
        tax = self._child(settlement, "ram", "ApplicableTradeTax")
        self._child(tax, "ram", "TypeCode", self.VAT)
        self._child(tax, "ram", "CategoryCode", self.STANDARD_CATEGORY)
        self._child(
            tax, "ram", "RateApplicablePercent", self._percentage(line.vat_rate)
        )
        period = self._child(settlement, "ram", "BillingSpecifiedPeriod")
        served = line.day if line.day else line.service_date
        self._date(period, "ram", "StartDateTime", f"{served:%Y%m%d}")
        self._date(period, "ram", "EndDateTime", f"{served:%Y%m%d}")
        summation = self._child(
            settlement, "ram", "SpecifiedTradeSettlementLineMonetarySummation"
        )
        self._child(summation, "ram", "LineTotalAmount", self._money(line.total_ht))

    def _delivery(self, parent: ElementTree.Element, bill: Bill) -> None:
        """Append where and when the care was delivered.

        Args:
            parent (ElementTree.Element): The transaction to append to.
            bill (Bill): The invoice being written.

        Notes:
            **The household goes here, even when somebody else is billed.** The
            ship-to party is where the work happened, which is what makes a
            funded invoice readable: a département receiving one for a hundred
            households can tell whose care each document covers.
        """
        delivery = self._child(parent, "ram", "ApplicableHeaderTradeDelivery")
        party = self._child(delivery, "ram", "ShipToTradeParty")
        self._child(party, "ram", "Name", bill.customer_full_name)
        self._address(party, bill.customer_address)
        event = self._child(delivery, "ram", "ActualDeliverySupplyChainEvent")
        self._date(event, "ram", "OccurrenceDateTime", f"{bill.period_end:%Y%m%d}")

    def _settlement(
        self, parent: ElementTree.Element, bill: Bill, company: Company
    ) -> None:
        """Append the money: the tax breakdown, the terms and the totals.

        Args:
            parent (ElementTree.Element): The transaction to append to.
            bill (Bill): The invoice being written.
            company (Company): The agency, for its bank account.

        Notes:
            The tax is broken down **per rate**, which is not a formality: a
            home-care invoice routinely carries assistance at the reduced rate
            beside comfort work at the standard one, and a single merged figure
            would be unusable by the recipient's own accounting.
        """
        settlement = self._child(parent, "ram", "ApplicableHeaderTradeSettlement")
        self._child(settlement, "ram", "InvoiceCurrencyCode", bill.CURRENCY)
        if company.iban:
            means = self._child(
                settlement, "ram", "SpecifiedTradeSettlementPaymentMeans"
            )
            self._child(means, "ram", "TypeCode", self.CREDIT_TRANSFER)
            account = self._child(means, "ram", "PayeePartyCreditorFinancialAccount")
            self._child(account, "ram", "IBANID", company.iban)
        for rate, base, tax_amount in bill.vat_by_rate():
            tax = self._child(settlement, "ram", "ApplicableTradeTax")
            self._child(tax, "ram", "CalculatedAmount", self._money(tax_amount))
            self._child(tax, "ram", "TypeCode", self.VAT)
            self._child(tax, "ram", "BasisAmount", self._money(base))
            self._child(tax, "ram", "CategoryCode", self.STANDARD_CATEGORY)
            self._child(tax, "ram", "RateApplicablePercent", self._percentage(rate))
        period = self._child(settlement, "ram", "BillingSpecifiedPeriod")
        self._date(period, "ram", "StartDateTime", f"{bill.period_start:%Y%m%d}")
        self._date(period, "ram", "EndDateTime", f"{bill.period_end:%Y%m%d}")
        terms = self._child(settlement, "ram", "SpecifiedTradePaymentTerms")
        self._date(terms, "ram", "DueDateDateTime", f"{bill.due_on:%Y%m%d}")

        totals = self._child(
            settlement,
            "ram",
            "SpecifiedTradeSettlementHeaderMonetarySummation",
        )
        self._child(totals, "ram", "LineTotalAmount", self._money(bill.total_ht))
        self._child(totals, "ram", "TaxBasisTotalAmount", self._money(bill.total_ht))
        tax_total = self._child(
            totals, "ram", "TaxTotalAmount", self._money(bill.total_vat)
        )
        tax_total.set("currencyID", bill.CURRENCY)
        self._child(totals, "ram", "GrandTotalAmount", self._money(bill.total_ttc))
        self._child(totals, "ram", "DuePayableAmount", self._money(bill.total_ttc))

    def _check_schema(self, payload: bytes, number: str) -> None:
        """Validate the file just built against the official schema.

        Args:
            payload (bytes): The XML that was produced.
            number (str): The invoice number, for the message.

        Raises:
            MTCiiNotSchemaValid: If the file does not satisfy the schema.

        Notes:
            - **This checks our own output, and it is cheap enough to always
              run.** The schema is what fixes the element order, and the order
              here is the order of the calls in :meth:`build` — so this is the
              test that a refactor did not quietly produce a file every platform
              will reject.
            - It is **not** the whole of conformance. The European business
              rules — the ones that check the totals add up and that every
              mandatory term is present — live in a Schematron that needs an
              XSLT 2.0 engine, which means a Saxon service this deployment does
              not run. Two things stand in for it: the schema below, and
              :meth:`~models.billing.bill.Bill.check_totals`, which refuses to
              build a bill whose totals disagree with its lines at all. The gap
              that remains is recorded in the design chapter rather than papered
              over here — calling the Schematron without a Saxon server returns
              success without checking anything, which is worse than not calling
              it.
        """
        try:
            xml_check_xsd(payload, flavor="factur-x", level="en16931")
        except Exception as exc:  # noqa: BLE001 - the library raises broadly
            self.logger.error(
                "The structured invoice built for %s does not satisfy the schema: %s.",
                number,
                exc,
            )
            raise MTCiiNotSchemaValid(
                f"The structured invoice for {number} is not schema-valid: {exc}"
            ) from exc
        self.logger.debug("The structured invoice for %s is schema-valid.", number)

    def _metadata(
        self, bill: Bill, company: Company, language: Language
    ) -> Dict[str, str]:
        """Return the document properties written into the file.

        Args:
            bill (Bill): The invoice being assembled.
            company (Company): The agency issuing it.
            language (Language): The language the page is written in.

        Returns:
            Dict[str, str]: Title, author, subject and keywords.

        Notes:
            Supplied rather than left to the library's own defaults, which
            derive a title from the file name — and this file has no name until
            somebody downloads it. The title is what a reader's tab shows and
            what an archive indexes on, so an invoice that says "invoice.pdf"
            there is one nobody finds again.
        """
        label = "Facture" if language is Language.FR else "Invoice"
        return {
            "title": f"{label} {bill.number} - {company.name}",
            "author": company.name,
            "subject": (
                f"{label} {bill.number} — {bill.describe_period()} — "
                f"{bill.total_ttc} {bill.CURRENCY}"
            ),
            "keywords": f"{label}, Factur-X, {bill.number}",
        }

    ############################
    # Publicly Exposed Methods #
    ############################

    def build(self, bill: Bill, company: Company) -> bytes:
        """Return the invoice as a structured CII document.

        Args:
            bill (Bill): The invoice to write.
            company (Company): The agency issuing it.

        Returns:
            bytes: The XML, encoded as UTF-8.

        Raises:
            MTCiiSellerNotIdentified: If the agency has no VAT number.
            MTCiiRecipientNotIdentified: If a professional buyer has no SIREN.
            MTCiiSplitNotRepresentable: If the invoice carries a funded share.

        Notes:
            The element order is the schema's, not a preference: the document,
            then every line, then the agreement, the delivery and the
            settlement. Reordering two calls in this method produces a file that
            still looks right and no validator accepts.
        """
        self.logger.debug("Building the structured invoice for %s.", bill.number)  # noqa: E501
        if bill.recipient.share_ttc is not None:
            self.logger.error(
                "Bill %s is split with a share of %s; the European rule set "
                "ties the amount due to the total less prepayments, so a share "
                "cannot be stated without calling the other party's part a "
                "prepayment.",
                bill.number,
                bill.recipient.share_ttc,
            )
            raise MTCiiSplitNotRepresentable(
                f"Invoice {bill.number} carries a funded share of "
                f"{bill.recipient.share_ttc}, which has no representation in "
                f"the structured format until the split is modelled."
            )

        for prefix, uri in self.NAMESPACES:
            ElementTree.register_namespace(prefix, uri)
        root = ElementTree.Element(self._qualified("rsm", "CrossIndustryInvoice"))  # noqa: E501

        context = self._child(root, "rsm", "ExchangedDocumentContext")
        guideline = self._child(
            context, "ram", "GuidelineSpecifiedDocumentContextParameter"
        )
        self._child(guideline, "ram", "ID", self.SPECIFICATION)

        document = self._child(root, "rsm", "ExchangedDocument")
        self._child(document, "ram", "ID", bill.number)
        self._child(document, "ram", "TypeCode", self.TYPE_CODE)
        self._date(document, "ram", "IssueDateTime", f"{bill.issued_on:%Y%m%d}")

        transaction = self._child(root, "rsm", "SupplyChainTradeTransaction")
        lines: List[BillLine] = bill.sorted_lines()
        for position, line in enumerate(lines, start=1):
            self._line(transaction, position, line)
        agreement = self._child(transaction, "ram", "ApplicableHeaderTradeAgreement")  # noqa: E501
        self._seller(agreement, company)
        self._buyer(agreement, bill)
        self._delivery(transaction, bill)
        self._settlement(transaction, bill, company)

        payload = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)  # noqa: E501
        self._check_schema(payload, bill.number)
        self.logger.info(
            "Built a %d-byte structured invoice for %s (%d line(s), %s TTC).",
            len(payload),
            bill.number,
            len(lines),
            bill.total_ttc,
        )
        return payload

    def assemble(
        self,
        pdf: bytes,
        xml: bytes,
        bill: Bill,
        company: Company,
        language: Language = Language.FR,
    ) -> bytes:
        """Return the rendered invoice carrying its structured twin.

        Args:
            pdf (bytes): The rendered page.
            xml (bytes): The structured invoice, already schema-checked.
            bill (Bill): The invoice, for the document properties.
            company (Company): The agency issuing it.
            language (Language): The language the page is written in.

        Returns:
            bytes: The Factur-X document.

        Raises:
            MTFacturXAssemblyFailed: If the two could not be combined.

        Notes:
            The schema check is left **on** even though the builder already ran
            it. It is milliseconds against a file that will be archived for ten
            years, and it is the one place that sees the exact bytes being
            embedded rather than the ones that were produced — which is what
            catches an encoding accident between the two.
        """
        self.logger.debug(
            "Assembling %s: %d bytes of page and %d of structured invoice.",
            bill.number,
            len(pdf),
            len(xml),
        )
        try:
            assembled = generate_from_binary(
                pdf,
                xml,
                flavor=self.FLAVOR,
                level=self.LEVEL,
                check_xsd=True,
                afrelationship=self.RELATIONSHIP,
                pdf_metadata=self._metadata(bill, company, language),
                lang=language.value,
            )
        except Exception as exc:  # noqa: BLE001 - the library raises broadly
            self.logger.error(
                "Could not build the Factur-X document for %s: %s.",
                bill.number,
                exc,
            )
            raise MTFacturXAssemblyFailed(
                f"The Factur-X document for {bill.number} "  # noqa: E501
                f"could not be built: {exc}"
            ) from exc
        self.logger.info(
            "Assembled Factur-X invoice %s (%d bytes, %s profile).",
            bill.number,
            len(assembled),
            self.LEVEL,
        )
        return assembled
