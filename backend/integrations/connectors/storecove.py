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


class StorecoveConnector(InvoicingConnector):
    """Talks to Storecove, an API-first platform and Peppol access point.

    Attributes:
        PROVIDER (ClassVar[EInvoicingProvider]): Storecove.
        DEFAULT_BASE_URL (ClassVar[str]): The production address.
        DOCUMENT_TYPE (ClassVar[str]): What a submission carries.
        PARSE_STRATEGY (ClassVar[str]): How the attached document is read.

    Notes:
        - **No Chorus Pro override, and that is the whole point.** Storecove's
          documentation covers French e-reporting and does not mention public
          bodies anywhere. Inheriting the base class's refusal means a conseil
          départemental's invoice is stopped here, with a message naming the
          problem, instead of being accepted and dropped somewhere nobody can
          see. Absent evidence, refusing is the recoverable error.
        - **The legal entity is created in Storecove's own console, not through
          this API.** That is a real constraint on setting an agency up rather
          than an oversight, which is why the descriptor declares
          ``legal_entity_id`` required and the dialog asks for it.
        - The document is sent base64-encoded inside the JSON submission rather
          than as a raw body: Storecove's submission is one JSON object carrying
          routing and payload together, and splitting it would be two calls the
          API does not offer.
        - Documentation read directly at ``storecove.com/docs``.
    """

    PROVIDER: ClassVar[EInvoicingProvider] = EInvoicingProvider.STORECOVE
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.storecove.com/api/v2"
    DOCUMENT_TYPE: ClassVar[str] = "invoice"
    PARSE_STRATEGY: ClassVar[str] = "cii"

    ############################
    # Internal Helpers Methods #
    ############################

    def _entity(self) -> str:
        """Return the legal entity submissions are made under.

        Returns:
            str: The configured entity, or an empty string.
        """
        return self.credentials.legal_entity_id or ""

    def _identifiers(self, bill: Bill) -> list:
        """Return how the recipient is addressed on the network.

        Args:
            bill (Bill): The invoice being transmitted.

        Returns:
            list: The recipient's electronic identifiers.

        Notes:
            ``0009`` is the Peppol scheme for a French SIRET/SIREN. A recipient
            with no identifier yields an empty list rather than a fabricated
            one — the platform then refuses the submission, which is correct:
            a business invoice with nobody to route to has no destination, and
            inventing a scheme would send it to whoever happens to hold that
            number.
        """
        siren = bill.recipient.siren
        if not siren:
            self.logger.warning(
                "Invoice %s has a recipient with no SIREN; Storecove has "
                "nothing to route on.",
                bill.number,
            )
            return []
        return [{"scheme": "0009", "id": siren}]

    def _reference(self, payload: JsonValue) -> str:
        """Return the submission guid out of a response body.

        Args:
            payload (JsonValue): The decoded JSON body.

        Returns:
            str: The guid, or an empty string when it is absent.

        Notes:
            Tolerant for the same reason B2Brouter's is: a missing identifier
            costs traceability, and raising over it would turn a transmitted
            invoice into a failed one after it had already gone.
        """
        if isinstance(payload, dict):
            for key in ("guid", "id"):
                found = payload.get(key)
                if found is not None:
                    return str(found)
        self.logger.warning(
            "Storecove returned no guid; the submission cannot be traced back "
            "to the platform."
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
        """Prove the key by reading the configured legal entity.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.

        Notes:
            Reads the *entity* rather than a generic endpoint, so one call
            proves both halves of what a manager typed: that the key works and
            that the legal-entity reference copied out of the console exists.
            Checking them separately would let a valid key with a mistyped
            entity pass the dialog and fail on the first invoice.
        """
        self.logger.debug(
            "Proving the Storecove key against legal entity %s.", self._entity()
        )
        await self._request("GET", f"/legal_entities/{self._entity()}")
        self.logger.info("Storecove accepted the credentials.")

    async def submit_invoice(self, bill: Bill, document: bytes) -> TransmissionReceipt:  # noqa: E501
        """Submit a structured invoice for delivery.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: Carrying Storecove's submission guid.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        self.logger.info("Submitting invoice %s to Storecove.", bill.number)
        response = await self._request(
            "POST",
            "/document_submissions",
            json_body={
                "legalEntityId": self._entity(),
                "routing": {"eIdentifiers": self._identifiers(bill)},
                "document": {
                    "documentType": self.DOCUMENT_TYPE,
                    "parseStrategy": self.PARSE_STRATEGY,
                    "rawDocumentData": base64.b64encode(document).decode("ascii"),  # noqa: E501
                },
            },
        )
        reference = self._reference(response.json())
        self.logger.info("Storecove accepted invoice %s (%s).", bill.number, reference)  # noqa: E501
        return self._sent(TransmissionKind.INVOICE, reference)

    async def report_payment(self, bill: Bill) -> TransmissionReceipt:
        """Declare that a settled invoice was collected.

        Args:
            bill (Bill): The settled invoice.

        Returns:
            TransmissionReceipt: Carrying the declaration's guid.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
        """
        self.logger.info(
            "Declaring collection of invoice %s to Storecove.", bill.number
        )
        response = await self._request(
            "POST",
            "/document_submissions",
            json_body={
                "legalEntityId": self._entity(),
                "document": {
                    "documentType": "invoice_response",
                    "invoiceNumber": bill.number,
                    "issueDate": bill.issued_on.isoformat(),
                    "amountTtc": str(bill.total_ttc),
                    "paid": True,
                },
            },
        )
        reference = self._reference(response.json())
        self.logger.info(
            "Storecove accepted the payment declaration for %s (%s).",
            bill.number,
            reference,
        )
        return self._sent(TransmissionKind.PAYMENT_REPORT, reference)
