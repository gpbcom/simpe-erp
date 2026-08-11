"""Building the documents a certified platform is handed.

Here rather than under ``service/utils`` because the only reason this code
exists is transmission: the structured invoice is what a platform reads, and
the reform is what requires one.
"""

from service.integrations.utils.factur_x import FacturXBuilder

__all__ = ["FacturXBuilder"]
