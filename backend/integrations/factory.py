from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Type

# Third-party imports
import httpx

# First-party imports
from integrations.base import InvoicingConnector
from integrations.connectors.b2brouter import B2BRouterConnector
from integrations.connectors.invopop import InvopopConnector
from integrations.connectors.iopole import IopoleConnector
from integrations.connectors.storecove import StorecoveConnector
from integrations.exceptions import MTConnectorNotImplemented
from models.enums import EInvoicingProvider
from models.integrations.integration_credentials import IntegrationCredentials


class ConnectorFactory:
    """Builds the connector for a platform.

    Attributes:
        CONNECTORS (ClassVar[Dict[EInvoicingProvider, Type[InvoicingConnector]]]):
            Platform to the class that speaks to it.
        logger (Logger): Logger for construction.

    Notes:
        - **One mapping, so nothing else branches on the enumeration.** Without
          it every caller wanting a connector would grow the same four-way
          ``if``, and a fifth platform would mean finding all of them.
        - Unknown platforms raise. A member of the enumeration with no connector
          is a programming error — the gallery would offer a card that cannot
          transmit — so it fails at construction rather than at the first paid
          invoice.
    """

    CONNECTORS: ClassVar[Dict[EInvoicingProvider, Type[InvoicingConnector]]] = {
        EInvoicingProvider.B2BROUTER: B2BRouterConnector,
        EInvoicingProvider.STORECOVE: StorecoveConnector,
        EInvoicingProvider.INVOPOP: InvopopConnector,
        EInvoicingProvider.IOPOLE: IopoleConnector,
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the factory.

        Args:
            logger (Optional[Logger]): Logger to use.
        """
        self.logger: Logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def build(
        self,
        provider: EInvoicingProvider,
        credentials: IntegrationCredentials,
        timeout_seconds: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> InvoicingConnector:
        """Return a connector ready to talk to a platform.

        Args:
            provider (EInvoicingProvider): The platform.
            credentials (IntegrationCredentials): What it authenticates on.
            timeout_seconds (float): How long to wait on it.
            client (Optional[httpx.AsyncClient]): A client to use instead of
                building one.

        Returns:
            InvoicingConnector: The connector.

        Raises:
            MTConnectorNotImplemented: If the platform has no connector, which
                can only happen if a member is added to the enumeration and not
                to this map.
        """
        connector_class = self.CONNECTORS.get(provider)
        if connector_class is None:
            self.logger.error(
                "No connector for %r. "  # noqa: E501
                "The enumeration and the factory have diverged.",
                provider,
            )
            raise MTConnectorNotImplemented(
                f"No connector for {provider!r}. "  # noqa: E501
                "The enumeration and the "
                f"factory have diverged."
            )
        self.logger.debug("Building the %s connector.", provider.value)
        return connector_class(
            credentials=credentials,
            timeout_seconds=timeout_seconds,
            client=client,
            logger=self.logger,
        )
