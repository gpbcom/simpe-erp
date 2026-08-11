class MTInvalidTransmissionReceiptException(Exception):
    """Exception raised when an invalid TransmissionReceipt field is provided."""


class MTTransmissionReceiptInvalidProvider(MTInvalidTransmissionReceiptException):
    """Exception raised when the answering platform is missing or unknown."""


class MTTransmissionReceiptInvalidKind(MTInvalidTransmissionReceiptException):
    """Exception raised when what was transmitted is missing or unknown.

    Notes:
        There is no default. An invoice recorded as a payment declaration would
        satisfy an audit that should have failed.
    """


class MTTransmissionReceiptInvalidStatus(MTInvalidTransmissionReceiptException):
    """Exception raised when the outcome is missing or unknown."""


class MTTransmissionReceiptInvalidReference(MTInvalidTransmissionReceiptException):
    """Exception raised when the platform's own identifier is not usable text."""


class MTTransmissionReceiptInvalidError(MTInvalidTransmissionReceiptException):
    """Exception raised when the recorded failure is not text."""


class MTTransmissionReceiptContradictory(MTInvalidTransmissionReceiptException):
    """Exception raised when the outcome and the diagnosis disagree.

    Notes:
        Sent with an error attached, or failed with nothing to explain it.
        Either would make the stored history unusable at the moment somebody
        needed it — which is months later, when an invoice is disputed.
    """
