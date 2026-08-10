class MTInvalidCompanyViewException(Exception):
    """Exception raised when an agency projection is invalid."""


class MTCompanyViewInvalidName(MTInvalidCompanyViewException):
    """Exception raised when the trading name is empty."""


class MTCompanyViewInvalidIbanMaskFlag(MTInvalidCompanyViewException):
    """Exception raised when the masking flag is not a boolean.

    Notes:
        Refused rather than coerced, and for the same reason the flag exists at
        all: a client uses it to decide whether the number it holds is safe to
        send back. A string ``"false"`` is truthy, and a view that claimed to be
        masked when it was not would be discovered by the whole account number
        appearing on somebody's screen.
    """
