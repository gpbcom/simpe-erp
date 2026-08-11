"""Outbound clients for the third parties this application depends on.

A plain module rather than a distribution of its own: it is imported by
``service`` and by nothing else, and a package boundary around four HTTP
clients bought a lockfile entry and a build target for no isolation anybody
uses.

Kept outside ``service`` all the same, because these are I/O against APIs
somebody else versions — a change of supplier should be replaceable without
touching a domain rule.
"""

from integrations.base import InvoicingConnector
from integrations.factory import ConnectorFactory

__all__ = [
    "ConnectorFactory",
    "InvoicingConnector",
]
