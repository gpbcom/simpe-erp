from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from integrations.base import InvoicingConnector
from integrations.exceptions import MTInvoicingConnectorException
from integrations.factory import ConnectorFactory

# First-party imports
from models.billing.bill import Bill
from models.configuration.integration_config import IntegrationConfig
from models.enums import (
    EInvoicingProvider,
    TransmissionKind,
    TransmissionStatus,
)
from models.integrations.einvoicing_integration import EInvoicingIntegration
from models.integrations.integration_credentials import IntegrationCredentials
from models.integrations.transmission_receipt import TransmissionReceipt
from models.schemas.responses.integrations.integration_card_response import (
    IntegrationCardResponse,
)
from service.integrations.exceptions import (
    MTIntegrationCredentialsRefused,
    MTIntegrationNotConfigured,
    MTNoActivePlatform,
)
from service.security.credential_cipher import CredentialCipher
from service.security.exceptions import MTCredentialCipherUnreadable
from storage.repositories.integrations.einvoicing_integration import (
    EInvoicingIntegrationRepository,
)


class InvoicingService:
    """What an agency transmits through, and what it transmits.

    Attributes:
        integrations (EInvoicingIntegrationRepository): Where the connections
            are stored.
        cipher (CredentialCipher): Seals and opens the credentials.
        config (IntegrationConfig): Who the platforms are, and how long to wait
            on one.
        connectors (ConnectorFactory): Builds a client for a platform.
        logger (Logger): Logger for integration and transmission operations.

    Notes:
        - **Connecting a platform and using it are one subject.** Splitting them
          into two services meant one of them existed only to hold a reference
          to the other, and every caller had to know which of the two answered
          "can this agency transmit at all?".
        - **The credentials are proven before they are stored.** A key is
          checked against the live platform while the dialog is still open, so a
          mistyped one is reported where it was typed. The alternative is
          storing it, calling it enabled, and discovering weeks later that
          nothing has left the building — which is the exact failure this whole
          feature exists to prevent.
        - **Nothing here returns a secret.** The listing is assembled into
          :class:`~models.schemas.responses.integrations.integration_card_response.IntegrationCardResponse`,
          which has no field for one, and the plaintext exists only inside
          :meth:`connector_for` for the length of a call.
        - **The routing is not decided here.**
          :meth:`~models.enums.TransmissionKind.for_recipient` decides it, from
          the recipient's kind, and this service does as it is told. That keeps
          "what happens to a public body's invoice?" a question with one answer
          in the codebase rather than one per call site.
        - **A household's settled invoice is declared, not sent.** It is the
          common case — most of this agency's revenue is B2C — and the one a
          literal reading of "send the paid bill to the platform" gets wrong.
          Nothing reaches the customer; what reaches the administration is that
          money changed hands, which is mandatory for services because VAT falls
          due on collection.
        - The one-active rule is the repository's, enforced in a transaction and
          in a database index. This service does not re-implement it, because a
          second copy is a second thing to keep true.
    """

    def __init__(
        self,
        integrations: EInvoicingIntegrationRepository,
        cipher: CredentialCipher,
        config: IntegrationConfig,
        connectors: Optional[ConnectorFactory] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            integrations (EInvoicingIntegrationRepository): Where the
                connections are stored.
            cipher (CredentialCipher): Seals and opens the credentials.
            config (IntegrationConfig): Who the platforms are, and how long to
                wait on one.
            connectors (Optional[ConnectorFactory]): Builds a client for a
                platform.
            logger (Optional[Logger]): Logger to use.
        """
        self.integrations = integrations
        self.cipher = cipher
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.connectors = connectors if connectors else ConnectorFactory()
        self.logger.debug("InvoicingService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _dispatch(
        self,
        connector: InvoicingConnector,
        kind: TransmissionKind,
        bill: Bill,
        document: bytes,
    ) -> TransmissionReceipt:
        """Call whichever connector method the obligation calls for.

        Args:
            connector (InvoicingConnector): The platform's client.
            kind (TransmissionKind): What must be transmitted.
            bill (Bill): The settled invoice.
            document (bytes): Its structured document.

        Returns:
            TransmissionReceipt: What the platform said.

        Raises:
            MTInvoicingConnectorException: If the platform refused or could not
                be reached.

        Notes:
            Exhaustive over the enumeration with no ``else``. A fourth kind of
            transmission would fail to route here — loudly, at the branch —
            rather than silently taking whichever call happened to be last.
        """
        if kind is TransmissionKind.CHORUS_PRO:
            return await connector.submit_to_chorus_pro(bill, document)
        if kind is TransmissionKind.INVOICE:
            return await connector.submit_invoice(bill, document)
        return await connector.report_payment(bill)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def list_cards(self, company_id: str) -> List[IntegrationCardResponse]:  # noqa: E501
        """Return every platform, with this agency's state against each.

        Args:
            company_id (str): The agency.

        Returns:
            List[IntegrationCardResponse]: One card per supported platform,
            configured or not.

        Notes:
            **Every platform, always** — a gallery that showed only what an
            agency had already connected would be empty on the one screen whose
            job is to get something connected.
        """
        self.logger.debug("Listing integration cards for agency %s.", company_id)  # noqa: E501
        stored = {
            integration.provider: integration
            for integration in await self.integrations.list_for_company(company_id)  # noqa: E501
        }
        cards = [
            IntegrationCardResponse.describing(
                descriptor, stored.get(descriptor.provider)
            )  # noqa: E501
            for descriptor in self.config.all_providers()
        ]
        self.logger.info(
            "Agency %s sees %d platform(s), %d configured.",
            company_id,
            len(cards),
            len(stored),
        )
        return cards

    async def has_active_platform(self, company_id: str) -> bool:
        """Return whether the agency can transmit at all.

        Args:
            company_id (str): The agency.

        Returns:
            bool: ``True`` when something is enabled.

        Notes:
            What the warning banner is drawn from. Electronic invoicing is a
            legal obligation, so "nothing connected" is a state a screen must
            say out loud rather than one it merely renders as an empty list.
        """
        active = await self.integrations.get_enabled(company_id)
        if active is None:
            self.logger.warning(
                "Agency %s has no e-invoicing platform enabled.", company_id
            )
            return False
        return True

    async def enable(
        self,
        company_id: str,
        provider: EInvoicingProvider,
        credentials: IntegrationCredentials,
        actor: str,
    ) -> EInvoicingIntegration:
        """Prove a platform's credentials, store them, and make it the active one.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform to connect.
            credentials (IntegrationCredentials): What it authenticates on.
            actor (str): The account making the change.

        Returns:
            EInvoicingIntegration: The now-active integration.

        Raises:
            MTIntegrationCredentialsRefused: If the platform would not accept
                the credentials.

        Notes:
            - **Checked first, stored second.** Storing an unproven key would
              enable a platform that cannot be reached and clear the warning
              banner that was telling the truth.
            - The connector's own exception carries the actionable half — re-enter
              the key, or wait for the platform — so it is re-raised with that
              message rather than replaced by a generic one.
        """
        self.logger.info(
            "%s is connecting %s for agency %s.",
            actor,
            provider.value,
            company_id,  # noqa: E501
        )
        connector = self.connectors.build(
            provider, credentials, self.config.request_timeout_seconds
        )
        try:
            await connector.check_credentials()
        except MTInvoicingConnectorException as error:
            self.logger.error(
                "%s refused agency %s's credentials: %s",
                provider.value,
                company_id,
                error,
            )
            raise MTIntegrationCredentialsRefused(str(error)) from error
        stored = await self.integrations.enable(
            company_id=company_id,
            provider=provider,
            ciphertext=self.cipher.seal(credentials),
            hint=credentials.hint(),
            actor=actor,
        )
        await self.integrations.record_check(company_id, provider, None)
        self.logger.info(
            "Agency %s now transmits through %s.", company_id, provider.value
        )
        return stored

    async def disable(
        self, company_id: str, provider: EInvoicingProvider, actor: str
    ) -> EInvoicingIntegration:
        """Stop transmitting through a platform, keeping its credentials.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform to switch off.
            actor (str): The account making the change.

        Returns:
            EInvoicingIntegration: The disabled integration.

        Raises:
            MTIntegrationNotConfigured: If the agency never configured it.
        """
        self.logger.info(
            "%s is disconnecting %s for agency %s.",
            actor,
            provider.value,
            company_id,
        )
        stored = await self.integrations.disable(company_id, provider, actor)
        if stored is None:
            self.logger.warning(
                "Agency %s has no %s integration to disable.",
                company_id,
                provider.value,
            )
            raise MTIntegrationNotConfigured(
                f"This agency has not connected {provider.value}."
            )
        self.logger.info(
            "Agency %s no longer transmits through %s.",
            company_id,
            provider.value,  # noqa: E501
        )
        return stored

    async def verify(
        self, company_id: str, provider: EInvoicingProvider
    ) -> EInvoicingIntegration:
        """Prove stored credentials again and record what happened.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform to check.

        Returns:
            EInvoicingIntegration: The integration, carrying the result.

        Raises:
            MTIntegrationNotConfigured: If the agency never configured it.

        Notes:
            **Records the failure rather than raising it.** A key rotated at the
            far end is something a manager needs to see on the card, and an
            endpoint that answered 502 would leave the record still claiming the
            platform was healthy.
        """
        stored = await self.integrations.get_for_provider(company_id, provider)
        if stored is None:
            raise MTIntegrationNotConfigured(
                f"This agency has not connected {provider.value}."
            )
        connector = self.connectors.build(
            provider,
            self.cipher.open(stored.credential_ciphertext),
            self.config.request_timeout_seconds,
        )
        failure: Optional[str] = None
        try:
            await connector.check_credentials()
        except MTInvoicingConnectorException as error:
            self.logger.warning(
                "%s no longer accepts agency %s's stored credentials: %s",
                provider.value,
                company_id,
                error,
            )
            failure = str(error)
        checked = await self.integrations.record_check(company_id, provider, failure)  # noqa: E501
        return checked if checked is not None else stored

    async def connector(
        self, company_id: str, provider: EInvoicingProvider
    ) -> InvoicingConnector:
        """Return a connector built on an agency's stored credentials.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform.

        Returns:
            InvoicingConnector: A client ready to talk to the platform.

        Raises:
            MTIntegrationNotConfigured: If the agency never configured it.
            MTCredentialCipherUnreadable: If the stored credentials will not
                open under the configured key.

        Notes:
            **The only place the plaintext exists**, and only for the length of
            the call the caller is about to make. Nothing returns it, nothing
            logs it, and nothing stores it anywhere but the sealed column.
        """
        stored = await self.integrations.get_for_provider(company_id, provider)
        if stored is None:
            raise MTIntegrationNotConfigured(
                f"This agency has not connected {provider.value}."
            )
        self.logger.debug(
            "Opening agency %s's %s credentials for one call.",
            company_id,
            provider.value,
        )
        return self.connectors.build(
            provider,
            self.cipher.open(stored.credential_ciphertext),
            self.config.request_timeout_seconds,
        )

    async def transmit(self, bill: Bill, document: bytes) -> TransmissionReceipt:  # noqa: E501
        """Transmit a settled invoice under whichever obligation applies to it.

        Args:
            bill (Bill): The settled invoice.
            document (bytes): Its structured document, for the routes that need
                one.

        Returns:
            TransmissionReceipt: What the platform said, successful or not.

        Raises:
            MTNoActivePlatform: If the agency has connected nothing. This is the
                one failure that *is* raised, because it is not a transmission
                that went wrong — it is one that could not be attempted, and the
                answer is a screen telling somebody to connect a platform.

        Notes:
            - The kind is resolved before anything else so that the log line
              names what was attempted even when the attempt fails.
            - **A failure never propagates as an error.** Transmission runs after
              the payment is recorded, off the manager's click. The money is
              settled whatever the platform said, so a failure comes back as a
              receipt to be recorded and retried — an exception here would turn a
              working payment into a 500 on a webhook that would then be
              redelivered.
        """
        kind = TransmissionKind.for_recipient(bill.recipient.kind)
        active = await self.integrations.get_enabled(bill.company_id)
        if active is None:
            self.logger.error(
                "Invoice %s is settled and cannot be transmitted: agency %s has "
                "no e-invoicing platform enabled.",
                bill.number,
                bill.company_id,
            )
            raise MTNoActivePlatform(
                "No certified platform is enabled. Connect one from the billing "
                "settings; electronic invoicing is a legal obligation."
            )
        self.logger.info(
            "Transmitting invoice %s as %s through %s.",
            bill.number,
            kind.value,
            active.provider.value,
        )
        try:
            connector = await self.connector(bill.company_id, active.provider)  # noqa: E501
        except MTCredentialCipherUnreadable as error:
            self.logger.error(
                "Invoice %s could not be transmitted: agency %s's stored "
                "credentials will not open.",
                bill.number,
                bill.company_id,
            )
            return TransmissionReceipt(
                provider=active.provider,
                kind=kind,
                status=TransmissionStatus.FAILED,
                error=str(error),
            )
        try:
            return await self._dispatch(connector, kind, bill, document)
        except MTInvoicingConnectorException as error:
            self.logger.error(
                "%s refused invoice %s (%s): %s",
                active.provider.value,
                bill.number,
                kind.value,
                error,
            )
            return TransmissionReceipt(
                provider=active.provider,
                kind=kind,
                status=TransmissionStatus.FAILED,
                error=str(error),
            )
