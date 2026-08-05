class MTInvalidInterventionTypeCatalogException(Exception):
    """Exception raised when a catalog operation fails."""


class MTInterventionTypeNotFound(MTInvalidInterventionTypeCatalogException):
    """Exception raised when the named intervention type does not exist."""


class MTInterventionTypeAlreadyExists(MTInvalidInterventionTypeCatalogException):
    """Exception raised when the name or code is already used by a type."""
