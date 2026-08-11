class MTInvalidAuthException(Exception):
    """Exception raised when an authentication operation fails."""


class MTAuthInvalidCredentials(MTInvalidAuthException):
    """Exception raised when the address or password does not match."""


class MTAuthUserInactive(MTInvalidAuthException):
    """Exception raised when a deactivated account attempts to sign in."""


class MTAuthEmailAlreadyRegistered(MTInvalidAuthException):
    """Exception raised when a registration reuses a known address."""


class MTAuthMissingSecret(MTInvalidAuthException):
    """Exception raised when the JWT signing secret is not configured."""


class MTAuthInvalidToken(MTInvalidAuthException):
    """Exception raised when an access token is malformed, expired or forged."""


class MTAuthHcaLinkRequired(MTInvalidAuthException):
    """Exception raised when an assistant account names no assistant record."""


class MTAuthUnknownHca(MTInvalidAuthException):
    """Exception raised when an assistant account names an unknown record."""


class MTAuthUnknownCustomer(MTInvalidAuthException):
    """Exception raised when a customer account names an unknown household."""


class MTAuthCustomerAlreadyHasAccount(MTInvalidAuthException):
    """Exception raised when a household already has portal access.

    Notes:
        Refused rather than answered with a second set of credentials. Two
        accounts on one household is two people who each believe they are the
        one who cancelled a visit, and the second invitation would silently
        make the first manager's password useless.
    """


class MTAuthLastAdmin(MTInvalidAuthException):
    """Exception raised when the change would remove the last administrator."""


class MTAuthPasswordChangeRequired(MTInvalidAuthException):
    """Exception raised when an account must change its password first.

    Notes:
        Raised for every request such an account makes except the change
        itself. The specification calls the change mandatory, and a rule that
        only the login screen enforces is one any other client can walk past.
    """


class MTAuthSamePassword(MTInvalidAuthException):
    """Exception raised when the new password repeats the old one.

    Notes:
        Refused because the temporary password is one a second person has
        seen. "Changing" it to itself would leave that credential live while
        clearing the flag that says so.
    """


class MTAuthCompanyRequired(MTInvalidAuthException):
    """Exception raised when an account would be created with no agency.

    Notes:
        Every account belongs to exactly one agency, whatever its role. One
        without is invisible to per-company scoping and produces events that
        cannot be routed, so it is refused at creation rather than stored and
        puzzled over later.
    """


class MTAuthUnknownAccount(MTInvalidAuthException):
    """Exception raised when the named account does not exist."""
