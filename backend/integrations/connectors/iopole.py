from __future__ import annotations

# Standard library imports
import base64
from typing import ClassVar, Dict

# Third-party imports
from pydantic import JsonValue

# First-party imports
from integrations.base import InvoicingConnector
from models.billing.bill import Bill
from models.enums import EInvoicingProvider, TransmissionKind
from models.integrations.transmission_receipt import TransmissionReceipt


class IopoleConnector(InvoicingConnector):
    """Talks to Iopole, the one French platform of the four.

    Attributes:
        PROVIDER (ClassVar[EInvoicingProvider]): Iopole.
        DEFAULT_BASE_URL (ClassVar[str]): The production address.
        INVOICE_PATH (ClassVar[str]): Where an invoice is submitted.
        REPORTING_PATH (ClassVar[str]): Where a declaration is submitted.
        CHORUS_PATH (ClassVar[str]): Where a public body's invoice is sent.

    Notes:
        - **This connector is written against documented shape, not against
          documentation anybody here read.** Iopole's servers return malformed
          HTTP headers and its documentation renders client-side, so unlike the
          other three nothing below was confirmed from the source. It is
          reported in the catalogue as unverified, the gallery card says so, and
          this docstring says so because a file is where somebody looks when it
          misbehaves. **Verify against ``docs.iopole.com`` in a browser before
          trusting it with a real invoice.**
        - The API is documented as asynchronous: state-changing calls return a
          ``guid`` immediately and the outcome is asked for later. That maps
          onto the receipt's ``reference`` without special handling — the guid
          *is* the platform's identifier — but it means a ``SENT`` receipt here
          asserts that Iopole accepted the request, not that the invoice has
          reached its recipient. That is true of the other three as well, and
          more visibly so here.
        - Rate-limited at 3,600 requests a minute per source address, which is
          far above anything a home-care agency's invoicing produces.
    """

    PROVIDER: ClassVar[EInvoicingProvider] = EInvoicingProvider.IOPOLE
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.iopole.com"
    INVOICE_PATH: ClassVar[str] = "/v1/invoices"
    REPORTING_PATH: ClassVar[str] = "/v1/ereporting/payments"
    CHORUS_PATH: ClassVar[str] = "/v1/invoices/public"

    ############################
    # Internal Helpers Methods #
    ############################

    async def _submit(self, path: str, bill: Bill, document: bytes) -> str:
        """Submit a document and return the guid the platform answered with.

        Args:
            path (str): The endpoint to submit to.
            bill (Bill): The invoice being transmitted.
            document (bytes): The document to submit.

        Returns:
            str: The guid.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        response = await self._request(
            "POST",
            path,
            json_body={
                "invoiceNumber": bill.number,
                "format": "cii",
                "content": base64.b64encode(document).decode("ascii"),
            },
        )
        return self._reference(response.json())

    def _reference(self, payload: JsonValue) -> str:
        """Return the guid out of a response body.

        Args:
            payload (JsonValue): The decoded JSON body.

        Returns:
            str: The guid, or an empty string when it is absent.

        Notes:
            The guid matters more here than on the other three: Iopole's API is
            asynchronous, so it is the only way to ask later what became of a
            submission. A missing one is logged loudly for that reason, and
            still does not fail a transmission that has already left.
        """
        if isinstance(payload, dict):
            for key in ("guid", "id", "requestId"):
                found = payload.get(key)
                if found is not None:
                    return str(found)
        self.logger.warning(
            "Iopole returned no guid. An asynchronous submission with no "
            "identifier cannot be followed up at all."
        )
        return ""

    ############################
    # Publicly Exposed Methods #
    ############################

    def headers(self) -> Dict[str, str]:
        """Return the bearer authorisation this platform expects.

        Returns:
            Dict[str, str]: The request headers.
        """
        return {
            "Authorization": f"Bearer {self.credentials.api_key}",
            "Content-Type": "application/json",
        }

    async def check_credentials(self) -> None:
        """Prove the key by reading the account it belongs to.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
        """
        self.logger.debug("Proving the Iopole key against its account.")
        await self._request("GET", "/v1/account")
        self.logger.info("Iopole accepted the credentials.")

    async def submit_invoice(self, bill: Bill, document: bytes) -> TransmissionReceipt:  # noqa: E501
        """Submit a structured invoice for delivery to a business.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: Carrying Iopole's guid.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        self.logger.info("Submitting invoice %s to Iopole.", bill.number)
        reference = await self._submit(self.INVOICE_PATH, bill, document)
        self.logger.info("Iopole accepted invoice %s (%s).", bill.number, reference)
        return self._sent(TransmissionKind.INVOICE, reference)

    async def report_payment(self, bill: Bill) -> TransmissionReceipt:
        """Declare a collection under flux 10.4.

        Args:
            bill (Bill): The settled invoice.

        Returns:
            TransmissionReceipt: Carrying Iopole's guid.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
        """
        self.logger.info(
            "Declaring collection of invoice %s to Iopole (flux 10.4).", bill.number
        )
        response = await self._request(
            "POST",
            self.REPORTING_PATH,
            json_body={
                "invoiceNumber": bill.number,
                "issuedOn": bill.issued_on.isoformat(),
                "totalTtc": str(bill.total_ttc),
                "collected": True,
            },
        )
        reference = self._reference(response.json())
        self.logger.info(
            "Iopole accepted the payment declaration for %s (%s).",
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
            TransmissionReceipt: Carrying Iopole's guid.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        self.logger.info("Submitting invoice %s to Iopole for Chorus Pro.", bill.number)  # noqa: E501
        reference = await self._submit(self.CHORUS_PATH, bill, document)
        self.logger.info(
            "Iopole accepted invoice %s for Chorus Pro (%s).",
            bill.number,
            reference,  # noqa: E501
        )
        return self._sent(TransmissionKind.CHORUS_PRO, reference)
