"""The two ways a Factur-X invoice can fail to be produced.

Two families rather than one, because they fail for different reasons and
an operator does different things about them: a structured invoice that
cannot be written is a record that is missing something, while an assembly
failure is the library refusing to combine two files that were both fine.
"""


class MTInvalidCiiInvoiceException(Exception):
    """Exception raised when a structured invoice cannot be built."""


class MTCiiSellerNotIdentified(MTInvalidCiiInvoiceException):
    """Exception raised when the agency lacks an identifier the format needs.

    Notes:
        A structured invoice naming standard-rated VAT must carry the seller's
        intra-community VAT number — the European rule set refuses one without
        it. Raised rather than omitted, because a file that is silently
        non-conforming is discovered when a platform rejects it, which is after
        a number has been drawn from a series that cannot have gaps.
    """


class MTCiiRecipientNotIdentified(MTInvalidCiiInvoiceException):
    """Exception raised when a professional recipient cannot be routed to.

    Notes:
        The buyer's legal identifier is what the invoice is delivered on. The
        model already refuses a professional without one. This catches the case
        where a record predating that rule reaches the builder.
    """


class MTCiiNotSchemaValid(MTInvalidCiiInvoiceException):
    """Exception raised when the file we just built fails its own schema.

    Notes:
        **A self-check, not a caller's mistake.** The element order in the
        format is part of the schema, so moving two lines in the builder
        produces a file that reads correctly and no platform accepts. Validating
        our own output on the way out turns that into a failure at the moment of
        the change, rather than a rejection weeks later against an invoice
        number that cannot be reissued.
    """


class MTCiiSplitNotRepresentable(MTInvalidCiiInvoiceException):
    """Exception raised when a funded share is asked for in structured form.

    Notes:
        **A deliberate refusal, not a missing feature.** The European rule set
        ties the amount due to the invoice total less what was prepaid, so a
        share owed by one of two payers can only be expressed by declaring the
        other party's part as a prepayment — which it is not. Whether a split
        arrangement is one invoice with two recipients or two linked invoices is
        a question the design chapter leaves open, and inventing an answer here
        would bury it in a file nobody reads until an auditor does.
    """


class MTInvalidFacturXException(Exception):
    """Exception raised when a Factur-X document cannot be produced."""


class MTFacturXAssemblyFailed(MTInvalidFacturXException):
    """Exception raised when the XML could not be attached to the PDF.

    Notes:
        Raised rather than falling back to the plain PDF. The two documents look
        alike in a reader and are not alike at all to a platform: one carries
        the structured invoice and one is a picture of it. Silently shipping the
        second is how an agency discovers, months later, that nothing it sent
        was ever machine-readable.
    """
