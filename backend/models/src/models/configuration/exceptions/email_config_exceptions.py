class MTInvalidEmailConfigException(Exception):
    """Exception raised when an invalid EmailConfig field is provided."""


class MTEmailConfigInvalidHost(MTInvalidEmailConfigException):
    """Exception raised when an invalid ``host`` value is provided."""


class MTEmailConfigInvalidPort(MTInvalidEmailConfigException):
    """Exception raised when an invalid ``port`` value is provided."""


class MTEmailConfigInvalidAddress(MTInvalidEmailConfigException):
    """Exception raised when an invalid email address is provided."""


class MTEmailConfigInvalidEnvName(MTInvalidEmailConfigException):
    """Exception raised when an invalid environment-variable name is provided."""


class MTEmailConfigMissingCredentials(MTInvalidEmailConfigException):
    """Exception raised when the SMTP credentials are absent from the environment."""


class MTInvalidWebhookConfigException(Exception):
    """Exception raised when an invalid WebhookConfig field is provided."""


class MTWebhookConfigInvalidUrl(MTInvalidWebhookConfigException):
    """Exception raised when an invalid ``url`` value is provided."""


class MTWebhookConfigInvalidEnvName(MTInvalidWebhookConfigException):
    """Exception raised when an invalid environment-variable name is provided."""


class MTWebhookConfigInvalidTimeout(MTInvalidWebhookConfigException):
    """Exception raised when an invalid ``timeout_seconds`` value is provided."""
