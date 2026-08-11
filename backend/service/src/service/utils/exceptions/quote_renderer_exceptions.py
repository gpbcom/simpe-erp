class MTInvalidQuoteRendererException(Exception):
    """Exception raised when a quote document cannot be produced."""


class MTQuoteRenderFailed(MTInvalidQuoteRendererException):
    """Exception raised when the document could not be laid out at all.

    Notes:
        Raised rather than reported, exactly as the invoice renderer does. The
        difference is what it costs: an invoice number is burnt on nothing,
        whereas a quote that will not render is an offer a household cannot
        read — a download button that answers an error page. Both need somebody
        to hear about it rather than a silent empty file.
    """
