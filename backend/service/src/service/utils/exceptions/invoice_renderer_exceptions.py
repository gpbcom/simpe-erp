class MTInvalidInvoiceRendererException(Exception):
    """Exception raised when an invoice document cannot be produced."""


class MTInvoiceRenderFailed(MTInvalidInvoiceRendererException):
    """Exception raised when the document could not be laid out at all.

    Notes:
        Raised rather than reported, unlike a missing logo. A document without
        its letterhead is still an invoice; a document that does not exist is a
        number burnt on nothing, and the generation run has to hear about it.
    """
