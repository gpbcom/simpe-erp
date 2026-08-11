class MTCredentialCipherException(Exception):
    """Exception raised when stored credentials cannot be sealed or opened."""


class MTCredentialCipherKeyUnusable(MTCredentialCipherException):
    """Exception raised when the configured key cannot drive the cipher.

    Notes:
        Raised at construction rather than at the first invoice. A deployment
        whose key is malformed cannot read a single stored credential, so
        failing where the service starts is the honest outcome — the
        alternative is a process that looks healthy and transmits nothing.
    """


class MTCredentialCipherUnreadable(MTCredentialCipherException):
    """Exception raised when a stored ciphertext will not open.

    Notes:
        Almost always a key that has been rotated or restored from the wrong
        secret store, rather than a corrupted row: Fernet authenticates what it
        encrypts, so a tampered or truncated value fails here rather than
        decrypting to something plausible.
    """
