from __future__ import annotations

# Standard library imports
from abc import ABC, abstractmethod
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional

# Third-party imports
import httpx
from pydantic import JsonValue

# First-party imports
from integrations.exceptions import (
    MTConnectorRejected,
    MTConnectorUnauthorised,
    MTConnectorUnavailable,
    MTConnectorUnsupported,
)
from models.billing.bill import Bill
from models.enums import (  # noqa: E501
    EInvoicingProvider,
    TransmissionKind,
    TransmissionStatus,
)
from models.integrations.integration_credentials import IntegrationCredentials
from models.integrations.transmission_receipt import TransmissionReceipt


class InvoicingConnector(ABC):
    """What every certified platform must be able to do, from here.

    Attributes:
        PROVIDER (ClassVar[EInvoicingProvider]): Which platform this speaks to.
        DEFAULT_BASE_URL (ClassVar[str]): The platform's published address.
        UNAUTHORISED (ClassVar[int]): The status meaning "your key is wrong".
        SERVER_ERROR (ClassVar[int]): Where a platform's own faults begin.
        credentials (IntegrationCredentials): What the platform authenticates on.
        timeout_seconds (float): How long to wait.
        logger (Logger): Logger for platform exchanges.

    Notes:
        - **Three methods, because the reform has three obligations**, not
          because three seemed tidy. An invoice to a business is routed to a
          recipient; a household's settled invoice is *declared* and reaches
          nobody; a public body is reached through Chorus Pro. A connector with
          one ``send`` would have to be told which of the three it was doing
          anyway, and the caller would be the one deciding — which is exactly
          the decision :meth:`~models.enums.TransmissionKind.for_recipient`
          exists to centralise.
        - **Failures are classified, not merely raised.** "The key is wrong" is
          the only one an agency can fix alone; "the platform is down" is worth
          retrying; "the document was refused" is neither, and is expensive
          because the invoice has already consumed a number. Collapsing them
          into one exception would put that judgement in a log message.
        - **Chorus Pro has a default that refuses.** A platform documenting no
          route to public bodies must say so rather than accept the invoice and
          drop it, which is indistinguishable from success until a conseil
          départemental asks where its money is.
        - The HTTP client is injected so the suite can drive a connector through
          ``httpx.MockTransport`` against recorded responses. Without that, the
          only way to test these is to hold four sandbox accounts.
    """

    PROVIDER: ClassVar[EInvoicingProvider]
    DEFAULT_BASE_URL: ClassVar[str]
    UNAUTHORISED: ClassVar[int] = 401
    SERVER_ERROR: ClassVar[int] = 500

    def __init__(
        self,
        credentials: IntegrationCredentials,
        timeout_seconds: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the connector.

        Args:
            credentials (IntegrationCredentials): What the platform
                authenticates on.
            timeout_seconds (float): How long to wait on the platform.
            client (Optional[httpx.AsyncClient]): An client to use instead of
                building one. The suite passes a mock transport through here.
            logger (Optional[Logger]): Logger to use.
        """
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds
        self.logger: Logger = logger if logger else getLogger(__name__)
        self.client = client
        self.logger.debug(
            "Connector for %s ready against %s.",
            self.PROVIDER.value,
            self.base_url(),
        )

    ############################
    # Internal Helpers Methods #
    ############################

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, JsonValue]] = None,
        content: Optional[bytes] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Make one call to the platform and classify anything that went wrong.

        Args:
            method (str): The HTTP method.
            path (str): The path, joined onto the base address.
            json_body (Optional[Dict[str, JsonValue]]): A JSON body, if any.
            content (Optional[bytes]): A raw body, if any.
            extra_headers (Optional[Dict[str, str]]): Headers for this call.

        Returns:
            httpx.Response: The platform's answer, already known to be a
            success.

        Raises:
            MTConnectorUnauthorised: On 401 or 403.
            MTConnectorUnavailable: On a transport failure or a 5xx.
            MTConnectorRejected: On any other 4xx.

        Notes:
            - **The classification is the point of this method.** Every connector
              needs the same three-way judgement and would otherwise write it four
              times, differently — and the difference that matters is whether an
              operator is told to fix their key, wait, or issue a credit note.
            - The response body is included in the rejection message and truncated
              by the receipt that stores it. It is the only description of what a
              platform disliked, and without it a refusal is unactionable.
        """
        headers = dict(self.headers())
        if extra_headers:
            headers.update(extra_headers)
        url = f"{self.base_url()}{path}"
        self.logger.debug("%s %s on %s.", method, path, self.PROVIDER.value)
        try:
            response = await self._send(method, url, headers, json_body, content)  # noqa: E501
        except httpx.HTTPError as error:
            self.logger.error(
                "%s could not be reached at %s: %s",
                self.PROVIDER.value,
                url,
                error,  # noqa: E501
            )
            raise MTConnectorUnavailable(
                f"{self.PROVIDER.value} could not be reached. The transmission "
                f"will be attempted again."
            ) from error
        if response.status_code in (self.UNAUTHORISED, 403):
            self.logger.error(
                "%s refused the credentials (%d).",
                self.PROVIDER.value,
                response.status_code,
            )
            raise MTConnectorUnauthorised(
                f"{self.PROVIDER.value} refused the credentials. Enter the "
                f"platform's API key again."
            )
        if response.status_code >= self.SERVER_ERROR:
            self.logger.error(
                "%s answered %d; it is unavailable.",
                self.PROVIDER.value,
                response.status_code,
            )
            raise MTConnectorUnavailable(
                f"{self.PROVIDER.value} answered {response.status_code}. The "
                f"transmission will be attempted again."
            )
        if response.status_code >= 400:
            self.logger.error(
                "%s rejected the document (%d): %s",
                self.PROVIDER.value,
                response.status_code,
                response.text[:200],
            )
            raise MTConnectorRejected(
                f"{self.PROVIDER.value} rejected the document "
                f"({response.status_code}): {response.text[:200]}"
            )
        self.logger.info(
            "%s accepted %s %s with %d.",
            self.PROVIDER.value,
            method,
            path,
            response.status_code,
        )
        return response

    async def _send(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_body: Optional[Dict[str, JsonValue]],
        content: Optional[bytes],
    ) -> httpx.Response:
        """Issue the call on the injected client, or on one built for it.

        Args:
            method (str): The HTTP method.
            url (str): The absolute address.
            headers (Dict[str, str]): The request headers.
            json_body (Optional[Dict[str, JsonValue]]): A JSON body, if any.
            content (Optional[bytes]): A raw body, if any.

        Returns:
            httpx.Response: The platform's answer.

        Notes:
            An injected client is *not* closed here — it belongs to whoever
            passed it, and closing somebody else's client is how a suite's
            second test finds a shut transport.
        """
        if self.client is not None:
            return await self.client.request(
                method, url, headers=headers, json=json_body, content=content
            )
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.request(
                method, url, headers=headers, json=json_body, content=content
            )

    def _sent(
        self, kind: TransmissionKind, reference: Optional[str]
    ) -> TransmissionReceipt:  # noqa: E501
        """Build the receipt for a transmission the platform accepted.

        Args:
            kind (TransmissionKind): What was transmitted.
            reference (Optional[str]): The platform's own identifier.

        Returns:
            TransmissionReceipt: The receipt.
        """
        return TransmissionReceipt(
            provider=self.PROVIDER,
            kind=kind,
            status=TransmissionStatus.SENT,
            reference=reference,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def base_url(self) -> str:
        """Return the address this connector talks to.

        Returns:
            str: The configured override, or the platform's published address.

        Notes:
            The override exists so a sandbox can be pointed at without a
            release, which is the only way an agency can rehearse a transmission
            before its first real invoice.
        """
        return self.credentials.base_url or self.DEFAULT_BASE_URL

    @abstractmethod
    def headers(self) -> Dict[str, str]:
        """Return the headers this platform authenticates on.

        Returns:
            Dict[str, str]: The request headers.

        Notes:
            Declared per platform because the four disagree entirely: a bearer
            token, a bespoke key header with a version beside it, and so on.
        """

    @abstractmethod
    async def check_credentials(self) -> None:
        """Prove the credentials against the platform.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.

        Notes:
            Called while the enable dialog is still open, so a mistyped key is
            reported where it was typed rather than by an invoice that silently
            never left weeks later.
        """

    @abstractmethod
    async def submit_invoice(self, bill: Bill, document: bytes) -> TransmissionReceipt:  # noqa: E501
        """Hand a structured invoice to the platform for delivery to a business.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: What the platform said.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.
            MTConnectorRejected: If the platform refused the document.
        """

    @abstractmethod
    async def report_payment(self, bill: Bill) -> TransmissionReceipt:
        """Declare that a settled invoice was collected.

        Args:
            bill (Bill): The settled invoice.

        Returns:
            TransmissionReceipt: What the platform said.

        Raises:
            MTConnectorUnauthorised: If the platform rejected the key.
            MTConnectorUnavailable: If the platform could not be reached.

        Notes:
            **Nothing reaches the customer.** This is e-reporting: the
            transaction and its collection are declared to the tax authority,
            because VAT on services falls due on collection rather than on
            delivery. It is what most of this agency's revenue produces.
        """

    async def submit_to_chorus_pro(
        self, bill: Bill, document: bytes
    ) -> TransmissionReceipt:
        """Route an invoice to a public body through Chorus Pro.

        Args:
            bill (Bill): The invoice being transmitted.
            document (bytes): The Factur-X or CII document.

        Returns:
            TransmissionReceipt: What the platform said.

        Raises:
            MTConnectorUnsupported: Unless the platform overrides this.

        Notes:
            **The default refuses**, and that is the safe direction. A platform
            whose documentation says nothing about public bodies is one this
            application must not hand a département's invoice to — accepting it
            and dropping it looks exactly like success.
        """
        self.logger.error(
            "%s cannot route invoice %s to Chorus Pro; the platform documents "
            "no route to public bodies.",
            self.PROVIDER.value,
            bill.number,
        )
        raise MTConnectorUnsupported(
            f"{self.PROVIDER.value} cannot transmit to a public body. Connect a "
            f"platform that reaches Chorus Pro, or invoice the département "
            f"through its own portal."
        )
