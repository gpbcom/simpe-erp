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


class InvopopConnector(InvoicingConnector):
    """Talks to Invopop, whose API is built around the open GOBL format.

    Attributes:
        PROVIDER (ClassVar[EInvoicingProvider]): Invopop.
        DEFAULT_BASE_URL (ClassVar[str]): The production address.
        SILO_PATH (ClassVar[str]): Where documents are stored.
        TRANSFORM_PATH (ClassVar[str]): Where workflows are run.
        FRENCH_FLOWS (ClassVar[Dict[str, str]]): Flux names, per obligation.

    Notes:
        - **Two calls, because the API is two services.** A document is put in
          the Silo and a job in Transform runs a workflow over it. That is not
          this connector being cautious — it is the shape of the platform, and
          it happens to give the same separation between "stored" and
          "transmitted" that B2Brouter's import-then-send does.
        - **The most explicitly documented French coverage of the four.** Flux 2
          and 6 for domestic B2B, 10.1 to 10.4 for reporting, and Chorus Pro as
          a separate integration. The flux names are carried here rather than
          inferred so that reading this file answers "what did we declare?".
        - The document is attached as a file rather than converted into GOBL.
          Invopop will happily build the invoice from GOBL JSON; sending the
          document this application already produces keeps the invoice's legal
          content out of a vendor's schema — the same trade every connector
          here makes.
        - Documentation read directly at ``docs.invopop.com``.
    """

    PROVIDER: ClassVar[EInvoicingProvider] = EInvoicingProvider.INVOPOP
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.invopop.com"
    SILO_PATH: ClassVar[str] = "/silo/v1/entries"
    TRANSFORM_PATH: ClassVar[str] = "/transform/v1/jobs"
    FRENCH_FLOWS: ClassVar[Dict[str, str]] = {
        "invoice": "fr-pa-invoice",
        "payment": "fr-pa-ereporting-10-4",
        "chorus": "fr-pa-chorus-pro",
    }

    ############################
    # Internal Helpers Methods #
    ############################

    async def _store(self, bill: Bill, document: bytes) -> str:
        """Put the document in the Silo and return its entry identifier.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The document to store.

        Returns:
            str: The Silo entry identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        self.logger.info("Storing invoice %s in the Invopop silo.", bill.number)  # noqa: E501
        response = await self._request(
            "POST",
            self.SILO_PATH,
            json_body={
                "meta": {"invoice_number": bill.number},
                "attachment": {
                    "name": f"{bill.number}.xml",
                    "data": base64.b64encode(document).decode("ascii"),
                },
            },
        )
        entry = self._reference(response.json())
        self.logger.debug("Invopop stored invoice %s as %s.", bill.number, entry)  # noqa: E501
        return entry

    async def _run(self, workflow: str, entry: str, bill: Bill) -> str:
        """Run a workflow over a stored entry and return the job identifier.

        Args:
            workflow (str): The workflow to run.
            entry (str): The Silo entry to run it over.
            bill (Bill): The invoice, for the log line.

        Returns:
            str: The job identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        self.logger.info(
            "Running Invopop workflow %s over invoice %s.",
            workflow,
            bill.number,  # noqa: E501
        )
        response = await self._request(
            "POST",
            self.TRANSFORM_PATH,
            json_body={"workflow_id": workflow, "silo_entry_id": entry},
        )
        return self._reference(response.json())

    def _reference(self, payload: JsonValue) -> str:
        """Return an identifier out of a response body.

        Args:
            payload (JsonValue): The decoded JSON body.

        Returns:
            str: The identifier, or an empty string when it is absent.
        """
        if isinstance(payload, dict):
            for key in ("id", "job_id", "entry_id"):
                found = payload.get(key)
                if found is not None:
                    return str(found)
        self.logger.warning(
            "Invopop returned no identifier; the transmission cannot be traced "
            "back to the platform."
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
        """Prove the key by reading the workspace it belongs to.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
        """
        self.logger.debug("Proving the Invopop key against its workspace.")
        await self._request("GET", "/access/v1/workspace")
        self.logger.info("Invopop accepted the credentials.")

    async def submit_invoice(self, bill: Bill, document: bytes) -> TransmissionReceipt:  # noqa: E501
        """Store the invoice, then run the French B2B workflow over it.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: Carrying the job identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        entry = await self._store(bill, document)
        reference = await self._run(self.FRENCH_FLOWS["invoice"], entry, bill)
        self.logger.info("Invopop sent invoice %s (%s).", bill.number, reference)  # noqa: E501
        return self._sent(TransmissionKind.INVOICE, reference)

    async def report_payment(self, bill: Bill) -> TransmissionReceipt:
        """Declare a collection under flux 10.4.

        Args:
            bill (Bill): The settled invoice.

        Returns:
            TransmissionReceipt: Carrying the job identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.

        Notes:
            No document is stored first. A payment declaration is data about a
            transaction rather than a document to route, which is the whole
            difference between e-reporting and e-invoicing.
        """
        self.logger.info(
            "Declaring collection of invoice %s to Invopop (flux 10.4).",
            bill.number,
        )
        response = await self._request(
            "POST",
            self.TRANSFORM_PATH,
            json_body={
                "workflow_id": self.FRENCH_FLOWS["payment"],
                "data": {
                    "invoice_number": bill.number,
                    "issue_date": bill.issued_on.isoformat(),
                    "total_ttc": str(bill.total_ttc),
                    "collected": True,
                },
            },
        )
        reference = self._reference(response.json())
        self.logger.info(
            "Invopop accepted the payment declaration for %s (%s).",
            bill.number,
            reference,
        )
        return self._sent(TransmissionKind.PAYMENT_REPORT, reference)

    async def submit_to_chorus_pro(
        self, bill: Bill, document: bytes
    ) -> TransmissionReceipt:
        """Route an invoice to a public body through the Chorus Pro workflow.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: Carrying the job identifier.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """
        entry = await self._store(bill, document)
        reference = await self._run(self.FRENCH_FLOWS["chorus"], entry, bill)
        self.logger.info(
            "Invopop sent invoice %s to Chorus Pro (%s).",
            bill.number,
            reference,  # noqa: E501
        )
        return self._sent(TransmissionKind.CHORUS_PRO, reference)
