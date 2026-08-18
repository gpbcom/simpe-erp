# First-party imports
from models.base.exceptions import MTInvalidPersonException


class MTInvalidUserException(MTInvalidPersonException):
    """Exception raised when an invalid User field is provided.

    Notes:
        Descends from :class:`MTInvalidPersonException` because an account
        *is* a person here — :class:`~models.auth.user.User` extends
        :class:`~models.base.person.Person`. The API's status map still has a
        row of its own for this class, and the handler walks the ancestry
        outwards, so an account's failure is answered as an account's.
    """


class MTUserInvalidId(MTInvalidUserException):
    """Exception raised when an invalid ``id`` value is provided."""


class MTUserInvalidEmail(MTInvalidUserException):
    """Exception raised when an invalid ``email`` value is provided."""


class MTUserInvalidHashedPassword(MTInvalidUserException):
    """Exception raised when an invalid ``hashed_password`` value is provided."""


class MTUserInvalidRole(MTInvalidUserException):
    """Exception raised when an invalid ``role`` value is provided."""


class MTUserInvalidHcaId(MTInvalidUserException):
    """Exception raised when an invalid ``hca_id`` value is provided."""


class MTUserInvalidFullName(MTInvalidUserException):
    """Exception raised when an invalid ``full_name`` value is provided."""


class MTUserInvalidDate(MTInvalidUserException):
    """Exception raised when an invalid timestamp value is provided."""


class MTUserRoleHcaRequiresHcaId(MTInvalidUserException):
    """Exception raised when an HCA account is not linked to an HCA record."""


class MTUserInvalidCustomerId(MTInvalidUserException):
    """Exception raised when an invalid ``customer_id`` value is provided."""


class MTUserRoleCustomerRequiresCustomerId(MTInvalidUserException):
    """Exception raised when a customer account names no customer record.

    Notes:
        The mirror of :class:`MTUserRoleHcaRequiresHcaId`, and it matters more.
        Every portal route resolves the household from ``customer_id``. An
        account without one could read nothing — or, under a check written the
        forgiving way, everything.
    """


class MTUserCustomerLinkRequiresCustomerRole(MTInvalidUserException):
    """Exception raised when a non-customer account names a customer record.

    Notes:
        The rule runs **both ways** on purpose. A manager carrying a
        ``customer_id`` is not merely untidy: it is an account that satisfies
        the staff guards *and* resolves to one household, which is precisely the
        shape a privilege-escalation bug takes. Refused at construction, so the
        state cannot exist to be reasoned about.
    """


class MTUserInvalidMustChangePassword(MTInvalidUserException):
    """Exception raised when the forced-change flag is not a boolean."""


class MTUserInvalidAccountOrigin(MTInvalidUserException):
    """Exception raised when the account origin is not a known one."""


class MTUserInvalidCompanyId(MTInvalidUserException):
    """Exception raised when the company identifier is not a string."""


class MTUserInvalidPhotoUrl(MTInvalidUserException):
    """Exception raised when the portrait URL was not issued by this store.

    Notes:
        An account's portrait is uploaded through the API and written under a
        fixed key prefix, so a value that does not carry that prefix is a URL
        somebody supplied rather than one this application stored. Accepting
        one would make every screen showing an avatar fetch a remote image the
        agency does not control, disclosing each viewer's address to whoever
        hosts it.
    """


class MTUserStaffAccountNeedsChange(MTInvalidUserException):
    """Exception raised when a staff-created account waives its password change.

    Notes:
        An account created by an administrator starts with a password its owner
        has never seen chosen. Building one that is not required to change it
        would leave a credential a second person knows, which is the whole
        thing the mandatory change exists to end.
    """


class MTUserInvalidPhoneNumber(MTInvalidUserException):
    """Exception raised when an invalid ``phone_number`` value is provided.

    Notes:
        An account's number is optional — the contact details of somebody the
        agency schedules live on their assistant record, not on the credential
        — so this is raised only for a value that is present and unusable.
    """


class MTUserInvalidAddress(MTInvalidUserException):
    """Exception raised when an invalid ``address`` value is provided.

    Notes:
        Optional for the same reason as
        :class:`MTUserInvalidPhoneNumber`.
    """


class MTUserInvalidLanguage(MTInvalidUserException):
    """Exception raised when an invalid ``language`` value is provided.

    Notes:
        An unknown code is refused rather than falling back to French. A
        preference the account holder set and the server quietly ignored is
        worse than one it rejected: the screen would go on showing their
        choice while every document came out in the other language.
    """
