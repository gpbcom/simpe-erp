from __future__ import annotations

# Standard library imports
import base64
from logging import Logger, getLogger
from typing import ClassVar

# Third-party imports
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# First-party imports
from models.configuration.integration_config import IntegrationConfig
from models.integrations.integration_credentials import IntegrationCredentials
from service.security.exceptions import (
    MTCredentialCipherKeyUnusable,
    MTCredentialCipherUnreadable,
)


class CredentialCipher:
    """Seals a platform's credentials for storage, and opens them to make a call.

    Attributes:
        MIN_SECRET_LENGTH (ClassVar[int]): Shortest configured secret accepted.
        SALT (ClassVar[bytes]): The fixed salt the key is derived with.
        ITERATIONS (ClassVar[int]): PBKDF2 rounds.
        KEY_BYTES (ClassVar[int]): Length of the derived key.
        logger (Logger): Logger for cipher operations.

    Notes:
        - **Reversible on purpose, which is the whole reason this class exists
          rather than reusing what hashes passwords.** ``bcrypt`` is correct for
          a password because nothing ever needs it back. A connector must
          present the platform's API key on every call, so the stored form has
          to open. That makes the key material, not the algorithm, the thing
          protecting these rows.
        - **Fernet rather than raw AES**: it authenticates what it encrypts, so
          a row edited in the database fails to open instead of decrypting to
          something plausible. A cipher that silently returned rubbish would
          send an invoice with a corrupted key and report a 401 as the
          platform's fault.
        - **The configured secret is derived into a key rather than used as
          one.** An operator sets a strong string in a secret store; requiring
          it to be a 44-character urlsafe-base64 Fernet key would be an
          arbitrary demand on people who already have a way of generating
          secrets. PBKDF2 turns any secret into the right shape and adds cost
          against a weak one.
        - **The salt is fixed, and that is a considered trade rather than an
          oversight.** A per-deployment salt is itself a secret to store,
          restore and lose, and the threat this design actually guards against
          is an attacker holding a database dump *without* the environment. The
          derivation is defence in depth. The environment is the control.
        - **Derived once.** The class is built behind an ``lru_cache``-d
          factory, so the iteration count is paid at start-up rather than per
          request. Constructing one of these per call would put a third of a
          second in front of every invoice.
    """

    MIN_SECRET_LENGTH: ClassVar[int] = 16
    SALT: ClassVar[bytes] = b"simple-erp.einvoicing.credentials.v1"
    ITERATIONS: ClassVar[int] = 600_000
    KEY_BYTES: ClassVar[int] = 32

    def __init__(self, config: IntegrationConfig) -> None:
        """Build a cipher from the deployment's configured secret.

        Args:
            config (IntegrationConfig): Names the environment variable holding
                the secret.

        Raises:
            MTCredentialCipherKeyUnusable: If the secret is too short to be one,
                or the derived key will not drive Fernet.

        Notes:
            Raising here rather than at first use is deliberate: a deployment
            with an unusable key cannot read a single stored credential, so
            refusing to start is more honest than a process that looks healthy
            and quietly transmits nothing.
        """
        self.logger: Logger = getLogger(__name__)
        secret = config.get_credential_key()
        if len(secret) < self.MIN_SECRET_LENGTH:
            self.logger.error(
                "The credential encryption secret in %r is %d characters. At "
                "least %d are required.",
                config.credential_key_env,
                len(secret),
                self.MIN_SECRET_LENGTH,
            )
            raise MTCredentialCipherKeyUnusable(
                f"The secret in {config.credential_key_env!r} is too short. "
                f"At least {self.MIN_SECRET_LENGTH} characters are required."
            )
        self.logger.debug(
            "Deriving the credential key from %r with %d PBKDF2 rounds.",
            config.credential_key_env,
            self.ITERATIONS,
        )
        derivation = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_BYTES,
            salt=self.SALT,
            iterations=self.ITERATIONS,
        )
        derived = base64.urlsafe_b64encode(derivation.derive(secret.encode("utf-8")))
        try:
            self._fernet = Fernet(derived)
        except (ValueError, TypeError) as error:
            self.logger.error("The derived credential key is unusable: %s", error)
            raise MTCredentialCipherKeyUnusable(
                "The derived credential key is not a usable Fernet key."
            ) from error
        self.logger.info("Credential cipher ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def seal(self, credentials: IntegrationCredentials) -> str:
        """Return the encrypted form of a platform's credentials.

        Args:
            credentials (IntegrationCredentials): What the platform
                authenticates on.

        Returns:
            str: The ciphertext, safe to store.

        Notes:
            The credentials are serialised with ``model_dump`` rather than
            formatted, because the model's own ``__repr__`` and ``__str__`` are
            redacted — formatting them would faithfully encrypt the word
            "redacted".
        """
        self.logger.debug("Sealing credentials for storage.")
        payload = credentials.model_dump_json().encode("utf-8")
        sealed = self._fernet.encrypt(payload).decode("utf-8")
        self.logger.info("Sealed a platform credential of %d bytes.", len(sealed))  # noqa: E501
        return sealed

    def open(self, ciphertext: str) -> IntegrationCredentials:
        """Return the credentials held in a stored ciphertext.

        Args:
            ciphertext (str): What was stored by :meth:`seal`.

        Returns:
            IntegrationCredentials: The credentials, ready for a connector.

        Raises:
            MTCredentialCipherUnreadable: If the ciphertext will not open under
                the configured key.

        Notes:
            **The failure is reported without the ciphertext.** It is not the
            secret, but it is the only thing standing between a log reader and
            the secret if the key ever leaks, so it does not go into the
            application log either.

            Almost every real occurrence is a rotated key or a secret restored
            from the wrong store, rather than a corrupted row: Fernet
            authenticates its own output, so tampering fails here rather than
            producing plausible rubbish.
        """
        self.logger.debug("Opening a stored platform credential.")
        try:
            payload = self._fernet.decrypt(ciphertext.encode("utf-8"))
        except (InvalidToken, ValueError, TypeError) as error:
            self.logger.error(
                "A stored credential would not open under the configured key; "
                "the key has most likely been rotated or restored from the "
                "wrong secret store."
            )
            raise MTCredentialCipherUnreadable(
                "The stored credentials could not be decrypted. The encryption "
                "key has changed, so the platform's credentials must be "
                "entered again."
            ) from error
        self.logger.debug("Opened a stored platform credential.")
        return IntegrationCredentials.model_validate_json(payload)
