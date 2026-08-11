class MTInvalidProviderDescriptorException(Exception):
    """Exception raised when an invalid ProviderDescriptor field is provided."""


class MTProviderDescriptorInvalidProvider(MTInvalidProviderDescriptorException):
    """Exception raised when the platform is missing or unknown."""


class MTProviderDescriptorInvalidName(MTInvalidProviderDescriptorException):
    """Exception raised when the display name is missing or empty."""


class MTProviderDescriptorInvalidUrl(MTInvalidProviderDescriptorException):
    """Exception raised when a published address is not absolute HTTPS."""


class MTProviderDescriptorInvalidCoverage(MTInvalidProviderDescriptorException):
    """Exception raised when the declared coverage is empty or unknown.

    Notes:
        Empty is refused rather than tolerated. Coverage is what the gallery
        filters on and what the transmission service checks before sending, so a
        platform covering nothing would render under every tab and then refuse
        every invoice — a contradiction better raised where it is written.
    """


class MTProviderDescriptorInvalidFields(MTInvalidProviderDescriptorException):
    """Exception raised when the required credential fields are not usable.

    Notes:
        A platform asking for no credential at all cannot be authenticated
        against, and one asking for a field the credentials model has no room
        for would render a dialog whose input goes nowhere.
    """


class MTProviderDescriptorInvalidVerified(MTInvalidProviderDescriptorException):
    """Exception raised when the documentation-verified flag is not a boolean."""
