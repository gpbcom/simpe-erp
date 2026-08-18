from __future__ import annotations

# Standard library imports
from typing import ClassVar, Dict

# Third-party imports
from pydantic import JsonValue

# First-party imports
from integrations.base import InvoicingConnector
from models.billing.bill import Bill
from models.enums import EInvoicingProvider, TransmissionKind
from models.integrations.transmission_receipt import TransmissionReceipt


class B2BRouterConnector(InvoicingConnector):
    """Talks to B2Brouter, which routes to Peppol and to Chorus Pro.

    Attributes:
        PROVIDER (ClassVar[EInvoicingProvider]): B2Brouter.
        DEFAULT_BASE_URL (ClassVar[str]): The production address.
        API_VERSION (ClassVar[str]): The API version header value.
        KEY_HEADER (ClassVar[str]): The header the key goes in.
        VERSION_HEADER (ClassVar[str]): The header the version goes in.

    Notes:
        - **Import and send are two calls, deliberately.** The API accepts
          ``send_after_import`` to do both at once, and this connector does not
          use it. A single call makes a malformed payload and a transmitted
          invoice the same event. A rejected invoice has already consumed a
          number from a series that cannot have gaps, so it cannot be edited and
          re-sent — only corrected by a credit note.
        - **The import door, not the JSON door.** The API will build an invoice
          from structured JSON, and this application already builds an EN 16931
          document of its own. Sending ours keeps the invoice's legal content in
          this repository rather than in a vendor's schema, and makes a change
          of platform a change of base URL rather than a re-mapping of every
          field.
        - The account is part of the path, which is why
          :class:`~models.integrations.provider_descriptor.ProviderDescriptor`
          declares ``account_id`` required for this platform.
        - Documentation read directly at ``docs.b2brouter.net``.
    """

    PROVIDER: ClassVar[EInvoicingProvider] = EInvoicingProvider.B2BROUTER
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.b2brouter.net"
    API_VERSION: ClassVar[str] = "2024-01-01"
    KEY_HEADER: ClassVar[str] = "X-B2B-API-Key"
    VERSION_HEADER: ClassVar[str] = "X-B2B-API-Version"

    ############################
    # Internal Helpers Methods #
    ############################

    def _account(self) -> str:
        """Return the account identifier the path is built on.

        Returns:
            str: The configured account, or an empty string.

        Notes:
            Empty rather than raising: the descriptor already declares the field
            required, so an absent one is caught when the dialog is submitted.
            A second refusal here would report the same mistake twice, in a
            place with less context.
        """
        return self.credentials.account_id or ""

    def _reference(self, payload: JsonValue) -> str:
        """Return the platform's identifier out of a response body.

        Args:
            payload (JsonValue): The decoded JSON body.

        Returns:
            str: The identifier, or an empty string when the shape is not what
            the documentation describes.

        Notes:
            Tolerant on purpose. A missing identifier costs traceability, and a
            connector that raised over it would turn a *transmitted* invoice
            into a failed one — the worst possible trade, because the invoice
            has already gone.
        """
        if isinstance(payload, dict):
            for key in ("id", "invoice_id", "uuid"):
                found = payload.get(key)
                if found is not None:
                    return str(found)
        self.logger.warning(
            "B2Brouter returned no identifier. The transmission cannot be "
            "traced back to the platform."
        )
        return ""

    ############################
    # Publicly Exposed Methods #
    ############################

    def headers(self) -> Dict[str, str]:
        """Return the key and version headers this platform expects.

        Returns:
            Dict[str, str]: The request headers.
        """
        return {
            self.KEY_HEADER: self.credentials.api_key,
            self.VERSION_HEADER: self.API_VERSION,
            "Content-Type": "application/json",
        }

    async def check_credentials(self) -> None:
        """Prove the key by listing the account's contacts.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.

        Notes:
            A read rather than a write. Proving a key by creating something
            leaves debris in the agency's real account every time somebody
            opens the dialog and changes their mind.
        """
        self.logger.debug("Proving the B2Brouter key for account %s.", self._account())  # noqa: E501
        await self._request(
            "GET", f"/accounts/{self._account()}/contacts?offset=0&limit=1"
        )
        self.logger.info("B2Brouter accepted the credentials.")

    async def submit_invoice(self, bill: Bill, document: bytes) -> TransmissionReceipt:  # noqa: E501
        """Import the structured invoice, then send it.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: Carrying B2Brouter's own invoice identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        self.logger.info("Importing invoice %s into B2Brouter.", bill.number)
        imported = await self._request(
            "POST",
            f"/accounts/{self._account()}/invoices/import?send_after_import=false",  # noqa: E501
            content=document,
            extra_headers={"Content-Type": "application/octet-stream"},
        )
        reference = self._reference(imported.json())
        self.logger.debug(
            "B2Brouter imported invoice %s as %s.", bill.number, reference
        )
        await self._request("POST", f"/invoices/send_invoice/{reference}")
        self.logger.info("B2Brouter sent invoice %s (%s).", bill.number, reference)  # noqa: E501
        return self._sent(TransmissionKind.INVOICE, reference)

    async def report_payment(self, bill: Bill) -> TransmissionReceipt:
        """Declare that a settled invoice was collected.

        Args:
            bill (Bill): The settled invoice.

        Returns:
            TransmissionReceipt: Carrying the declaration's identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
        """
        self.logger.info(
            "Declaring collection of invoice %s to B2Brouter.", bill.number
        )
        response = await self._request(
            "POST",
            f"/accounts/{self._account()}/tax_reports",
            json_body={
                "invoice_number": bill.number,
                "issued_on": bill.issued_on.isoformat(),
                "total_ttc": str(bill.total_ttc),
                "collected": True,
            },
        )
        reference = self._reference(response.json())
        self.logger.info(
            "B2Brouter accepted the payment declaration for %s (%s).",
            bill.number,
            reference,
        )
        return self._sent(TransmissionKind.PAYMENT_REPORT, reference)

    async def submit_to_chorus_pro(
        self, bill: Bill, document: bytes
    ) -> TransmissionReceipt:
        """Route an invoice to a public body.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: Carrying B2Brouter's own invoice identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.

        Notes:
            The same import-then-send pair as an ordinary invoice: B2Brouter
            treats Chorus Pro as one of the networks it routes to, and the
            recipient's SIREN and service code — already on
            :class:`~models.billing.bill_recipient.BillRecipient` — are what
            decide the destination.
        """
        self.logger.info(
            "Importing invoice %s into B2Brouter for Chorus Pro.", bill.number
        )
        imported = await self._request(
            "POST",
            f"/accounts/{self._account()}/invoices/import?send_after_import=false",  # noqa: E501
            content=document,
            extra_headers={"Content-Type": "application/octet-stream"},
        )
        reference = self._reference(imported.json())
        await self._request("POST", f"/invoices/send_invoice/{reference}")
        self.logger.info(
            "B2Brouter sent invoice %s to Chorus Pro (%s).",
            bill.number,
            reference,  # noqa: E501
        )
        return self._sent(TransmissionKind.CHORUS_PRO, reference)
