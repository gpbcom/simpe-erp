"""Sealing the secrets this application holds on somebody else's behalf.

Passwords are hashed and never read back. A platform's API credentials must be,
because a connector presents them on every call. The two need different tools,
and keeping the reversible one here rather than beside the password hashing is
what stops the wrong one being reached for.
"""

from .credential_cipher import CredentialCipher

__all__ = ["CredentialCipher"]
