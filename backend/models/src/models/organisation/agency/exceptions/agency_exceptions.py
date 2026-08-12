class MTInvalidAgencyException(Exception):
    """Exception raised when an agency is invalid."""


class MTAgencyInvalidId(MTInvalidAgencyException):
    """Exception raised when the identifier is not a non-empty string."""


class MTAgencyInvalidCompanyId(MTInvalidAgencyException):
    """Exception raised when the owning company is not named.

    Notes:
        Required rather than optional, for the same reason ``company_id`` is
        required on an account and on an assistant: a site belonging to no
        company is covered by no scoping, and the state is refused rather than
        stored and puzzled over later.
    """


class MTAgencyInvalidName(MTInvalidAgencyException):
    """Exception raised when the site name is empty or too long."""


class MTAgencyInvalidAddress(MTInvalidAgencyException):
    """Exception raised when the address is not a postal address.

    Notes:
        Absence is not an error — a company founded through the public
        registration form supplies no address, so the head office created
        alongside it has none. What is refused is a value that is not an
        address *at all*, which would otherwise surface as a raw Pydantic error
        the API's exception map has no row for.
    """


class MTAgencyInvalidType(MTInvalidAgencyException):
    """Exception raised when the type is not an :class:`AgencyType`."""


class MTAgencyLegalIdentityMisplaced(MTInvalidAgencyException):
    """Exception raised when a branch carries the business's legal identity.

    Notes:
        A site inherits every attribute of the company because the head office
        *is* where the business is registered. A warehouse or a branch holding
        its own SIRET, VAT number and IBAN would print two different companies
        on two quotes from one agency, and route two different bank accounts on
        two invoices. There is one legal entity and one place it is registered.
    """


class MTAgencyInvalidDate(MTInvalidAgencyException):
    """Exception raised when a timestamp is not a datetime."""


class MTAgencyInvalidMembers(MTInvalidAgencyException):
    """Exception raised when the member list is malformed or repeats a person.

    Notes:
        A repeated person is refused rather than de-duplicated. The list is
        replaced wholesale by the form that edits it, so a duplicate is a
        caller sending something it did not mean — and silently collapsing it
        would hide the bug that produced it.
    """


class MTAgencyMemberInvalidKind(MTInvalidAgencyException):
    """Exception raised when the member kind is not a :class:`MemberKind`."""


class MTAgencyMemberInvalidId(MTInvalidAgencyException):
    """Exception raised when the member identifier is not a non-empty string."""
