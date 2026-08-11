"""One class per certified e-invoicing platform, all behind ``InvoicingConnector``.

What each platform documents — and, for one of them, what could not be read at
all — is recorded in ``docs/15-electronic-invoicing.md``.
"""

from integrations.connectors.b2brouter import B2BRouterConnector
from integrations.connectors.invopop import InvopopConnector
from integrations.connectors.iopole import IopoleConnector
from integrations.connectors.storecove import StorecoveConnector

__all__ = [
    "B2BRouterConnector",
    "InvopopConnector",
    "IopoleConnector",
    "StorecoveConnector",
]
