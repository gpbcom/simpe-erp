class MTInvalidCompanyException(Exception):
    """Exception raised when a company is invalid."""


class MTCompanyInvalidId(MTInvalidCompanyException):
    """Exception raised when the identifier is not a non-empty string."""


class MTCompanyInvalidName(MTInvalidCompanyException):
    """Exception raised when the trading name is empty or too long."""


class MTCompanyInvalidRegistrationNumber(MTInvalidCompanyException):
    """Exception raised when the registration number is malformed."""


class MTCompanyInvalidEmail(MTInvalidCompanyException):
    """Exception raised when the contact address is not an email address."""


class MTCompanyInvalidIsAcceptingApplications(MTInvalidCompanyException):
    """Exception raised when the open-to-applications flag is not a boolean."""


class MTCompanyInvalidDate(MTInvalidCompanyException):
    """Exception raised when a timestamp is not a datetime."""


class MTCompanyInvalidLegalForm(MTInvalidCompanyException):
    """Exception raised when the legal form is not a usable label.

    Notes:
        Free text rather than an enumeration, and refused only for being
        unusable. French home care is delivered by SARLs, SAS, associations,
        CCAS, mutuelles and sole traders alike. A closed list would lock out a
        provider whose form nobody thought of, on a field that only ever gets
        printed.
    """


class MTCompanyInvalidShareCapital(MTInvalidCompanyException):
    """Exception raised when the share capital is not a positive amount."""


class MTCompanyInvalidRcsNumber(MTInvalidCompanyException):
    """Exception raised when the RCS entry is not a usable label."""


class MTCompanyInvalidVatNumber(MTInvalidCompanyException):
    """Exception raised when the intra-community VAT number is malformed."""


class MTCompanyInvalidPhoneNumber(MTInvalidCompanyException):
    """Exception raised when the contact telephone number is not usable."""


class MTCompanyInvalidIban(MTInvalidCompanyException):
    """Exception raised when the IBAN is malformed or fails its checksum.

    Notes:
        The checksum is part of what makes an IBAN an IBAN, so a number that
        merely looks right is still refused. A transposed digit in an account a
        customer is asked to pay into is the kind of error that surfaces as a
        missing payment weeks later, not as a rejected form.
    """


class MTCompanyInvalidBic(MTInvalidCompanyException):
    """Exception raised when the BIC is not eight or eleven characters."""


class MTCompanyInvalidLogoUrl(MTInvalidCompanyException):
    """Exception raised when the logo URL was not issued by this application.

    Notes:
        A URL outside the application's own key prefix is refused rather than
        stored: the logo is rendered on every screen and on the quote, so a
        remote one would report every viewer to whoever hosts it, and the
        object store could not own the object it is later asked to remove.
    """


class MTCompanyInvalidSapDeclarationNumber(MTInvalidCompanyException):
    """Exception raised when an invalid SAP declaration number is provided.

    Notes:
        The *services à la personne* declaration number is what lets a customer
        claim the tax credit an invoice for home care entitles them to, so a
        malformed one is not a cosmetic defect: it is the one line on the
        document the customer will be asked to justify.
    """
