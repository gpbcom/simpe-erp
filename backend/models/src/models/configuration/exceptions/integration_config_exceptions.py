class MTInvalidIntegrationConfigException(Exception):
    """Exception raised when an invalid IntegrationConfig field is provided."""


class MTIntegrationConfigInvalidKeyEnv(MTInvalidIntegrationConfigException):
    """Exception raised when the credential-key variable is not named."""


class MTIntegrationConfigMissingKey(MTInvalidIntegrationConfigException):
    """Exception raised when the named environment variable holds no key.

    Notes:
        Raised at start-up rather than at the first invoice. A deployment with
        no key cannot decrypt a single stored credential, so failing to boot is
        the honest outcome — the alternative is a service that appears healthy
        and silently transmits nothing.
    """


class MTIntegrationConfigInvalidTimeout(MTInvalidIntegrationConfigException):
    """Exception raised when the platform request timeout is out of range."""


class MTIntegrationConfigInvalidProviders(MTInvalidIntegrationConfigException):
    """Exception raised when the declared platform catalogue is malformed.

    Notes:
        The catalogue is deployment configuration rather than code, which is
        what lets an operator add a platform without a release. The price is
        that a typo in ``app.yaml`` is a typo in the gallery, so the payload is
        refused at start-up rather than rendered as a card nobody can connect.
    """


class MTIntegrationConfigProviderUnknown(MTInvalidIntegrationConfigException):
    """Exception raised when a platform is asked for that was never declared.

    Notes:
        Raised rather than answered with ``None``: a caller writing ``or
        default`` around a miss would render a gallery card with no name, or
        transmit through a platform this deployment never configured.
    """
