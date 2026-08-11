class MTInvalidBillRecipientException(Exception):
    """Exception raised when an invalid BillRecipient field is provided."""


class MTBillRecipientInvalidKind(MTInvalidBillRecipientException):
    """Exception raised when the recipient is of no known kind.

    Notes:
        Refused rather than defaulted to an individual. The kind decides
        whether the invoice is *transmitted* to a platform or merely *reported*
        to the tax authority, so a wrong one is not a cosmetic error — it is the
        invoice taking the wrong regulatory path in silence.
    """


class MTBillRecipientInvalidName(MTInvalidBillRecipientException):
    """Exception raised when the recipient is not named."""


class MTBillRecipientInvalidAddress(MTInvalidBillRecipientException):
    """Exception raised when an invalid billing address is provided."""


class MTBillRecipientInvalidSiren(MTInvalidBillRecipientException):
    """Exception raised when a legal identifier is not a valid SIREN.

    Notes:
        The nine digits carry their own Luhn check, so a transposed pair is
        caught here rather than by the platform that could not route the
        invoice. A household has no SIREN at all, which is why the field is
        optional and only its *malformedness* is an error.
    """


class MTBillRecipientMissingSiren(MTInvalidBillRecipientException):
    """Exception raised when a professional recipient carries no SIREN.

    Notes:
        Separate from :class:`MTBillRecipientInvalidSiren` because the two send
        whoever is fixing it to different places: a malformed number is a typo
        on this invoice, and a missing one is a payer record nobody completed.
    """


class MTBillRecipientUnexpectedSiren(MTInvalidBillRecipientException):
    """Exception raised when a private individual is given a SIREN.

    Notes:
        Refused rather than ignored. A household with a legal identifier would
        be classified as a business by every downstream reader, and the invoice
        would be transmitted for delivery to a company that does not exist.
    """


class MTBillRecipientInvalidVatNumber(MTInvalidBillRecipientException):
    """Exception raised when an invalid intra-community VAT number is given."""


class MTBillRecipientInvalidServiceCode(MTInvalidBillRecipientException):
    """Exception raised when an invalid public-body service code is given.

    Notes:
        A public body routes an invoice to a *service* inside itself, not to
        the body as a whole. A wrong code delivers the document to an
        organisation that has no idea what it is for.
    """


class MTBillRecipientInvalidShare(MTInvalidBillRecipientException):
    """Exception raised when an invalid funded share is provided."""
