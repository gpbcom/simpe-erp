from __future__ import annotations

# Standard library imports
from typing import Iterator

# Third-party imports
import pytest

# First-party imports
from models.configuration.exceptions import MTIntegrationConfigMissingKey
from models.configuration.integration_config import IntegrationConfig
from models.integrations.integration_credentials import IntegrationCredentials
from service.security.credential_cipher import CredentialCipher
from service.security.exceptions import (
    MTCredentialCipherKeyUnusable,
    MTCredentialCipherUnreadable,
)

SECRET = "a-long-enough-development-secret"
OTHER_SECRET = "a-completely-different-secret-value"


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[IntegrationConfig]:
    """Point the configuration at a set environment variable.

    Args:
        monkeypatch (pytest.MonkeyPatch): The patcher.

    Yields:
        IntegrationConfig: A configuration whose key resolves.
    """
    config = IntegrationConfig()
    monkeypatch.setenv(config.credential_key_env, SECRET)
    yield config


@pytest.fixture
def cipher(configured: IntegrationConfig) -> CredentialCipher:
    """Build a cipher on the configured secret.

    Args:
        configured (IntegrationConfig): The configuration.

    Returns:
        CredentialCipher: The cipher.

    Notes:
        Deriving the key costs six hundred thousand PBKDF2 rounds, which is
        why production builds one per process behind an ``lru_cache``. Tests
        that only need *a* cipher share this one rather than paying again.
    """
    return CredentialCipher(configured)


def _credentials() -> IntegrationCredentials:
    """Return a full set of credentials.

    Returns:
        IntegrationCredentials: Every field populated.
    """
    return IntegrationCredentials(
        api_key="sk_live_0123456789abcdef",
        account_id="12345",
        legal_entity_id="98765",
        base_url="https://api-staging.b2brouter.net",
    )


class TestSealingAndOpening:
    """Tests for the round trip a stored credential makes."""

    def test_what_is_sealed_opens_again(self, cipher: CredentialCipher) -> None:
        """The whole point: a connector must get the key back.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        credentials = _credentials()

        assert cipher.open(cipher.seal(credentials)) == credentials

    def test_every_field_survives(self, cipher: CredentialCipher) -> None:
        """Not only the key — a platform routes on the references too.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        opened = cipher.open(cipher.seal(_credentials()))

        assert opened.account_id == "12345"
        assert opened.legal_entity_id == "98765"
        assert opened.base_url == "https://api-staging.b2brouter.net"

    def test_the_ciphertext_does_not_contain_the_key(
        self, cipher: CredentialCipher
    ) -> None:
        """Stating the obvious, because it is the reason this class exists.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        sealed = cipher.seal(_credentials())

        assert "sk_live_0123456789abcdef" not in sealed

    def test_sealing_twice_gives_different_ciphertexts(
        self, cipher: CredentialCipher
    ) -> None:
        """Fernet carries a random IV and a timestamp.

        Args:
            cipher (CredentialCipher): The cipher.

        Notes:
            Worth asserting because equal ciphertexts would let anybody with
            read access to the table learn that two agencies use the same key,
            which is a fact about a shared account they did not disclose.
        """
        credentials = _credentials()

        assert cipher.seal(credentials) != cipher.seal(credentials)

    def test_the_redacted_representation_is_not_what_gets_sealed(
        self, cipher: CredentialCipher
    ) -> None:
        """**The trap this class had to avoid.**

        Args:
            cipher (CredentialCipher): The cipher.

        Notes:
            The credentials model redacts its own ``__repr__`` and ``__str__``.
            A ``seal`` written with an f-string would faithfully encrypt the
            word "redacted" and every stored credential would be useless — and
            it would look like it worked.
        """
        opened = cipher.open(cipher.seal(_credentials()))

        assert opened.api_key == "sk_live_0123456789abcdef"


class TestRefusingToOpen:
    """Tests for the ciphertexts that must not yield credentials."""

    @pytest.mark.parametrize("value", ["", "not-a-token", "gAAAAA-nonsense"])
    def test_rubbish_will_not_open(self, cipher: CredentialCipher, value: str) -> None:
        """Args:
        cipher (CredentialCipher): The cipher.
        value (str): The rejected ciphertext.
        """
        with pytest.raises(MTCredentialCipherUnreadable):
            cipher.open(value)

    def test_a_tampered_ciphertext_fails_rather_than_decrypting(
        self, cipher: CredentialCipher
    ) -> None:
        """**Why Fernet rather than raw AES.**

        Args:
            cipher (CredentialCipher): The cipher.

        Notes:
            An unauthenticated cipher would decrypt an edited row to plausible
            rubbish, send an invoice with a corrupted key, and report the
            resulting 401 as the platform's fault.
        """
        sealed = cipher.seal(_credentials())

        with pytest.raises(MTCredentialCipherUnreadable):
            cipher.open(sealed[:-4] + "AAAA")

    def test_another_deployments_key_will_not_open_it(
        self, configured: IntegrationConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A credential sealed here is useless elsewhere.

        Args:
            configured (IntegrationConfig): The configuration.
            monkeypatch (pytest.MonkeyPatch): The patcher.

        Notes:
            The fixed salt means the derivation is the same everywhere. It is
            the *secret* that separates deployments, and this is the assertion
            that says so.
        """
        sealed = CredentialCipher(configured).seal(_credentials())
        monkeypatch.setenv(configured.credential_key_env, OTHER_SECRET)

        with pytest.raises(MTCredentialCipherUnreadable):
            CredentialCipher(configured).open(sealed)

    def test_the_failure_does_not_quote_the_ciphertext(
        self, cipher: CredentialCipher
    ) -> None:
        """It is not the secret, but it is the last thing guarding it.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        sealed = cipher.seal(_credentials())
        tampered = sealed[:-4] + "AAAA"

        with pytest.raises(MTCredentialCipherUnreadable) as raised:
            cipher.open(tampered)

        assert tampered not in str(raised.value)

    def test_the_failure_tells_an_operator_what_to_do(
        self, cipher: CredentialCipher
    ) -> None:
        """A rotated key is recoverable, but only by re-entering credentials.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        with pytest.raises(MTCredentialCipherUnreadable) as raised:
            cipher.open("not-a-token")

        assert "entered again" in str(raised.value)


class TestRefusingToStart:
    """Tests for the deployments that must not boot.

    Notes:
        Every failure here is raised at construction rather than at the first
        invoice. A process that cannot read a stored credential and starts
        anyway looks healthy and transmits nothing, which is the exact failure
        this feature exists to prevent.
    """

    def test_an_unset_key_refuses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """There is deliberately no default.

        Args:
            monkeypatch (pytest.MonkeyPatch): The patcher.
        """
        config = IntegrationConfig()
        monkeypatch.delenv(config.credential_key_env, raising=False)

        with pytest.raises(MTIntegrationConfigMissingKey):
            CredentialCipher(config)

    @pytest.mark.parametrize("secret", ["short", "0123456789abcde"])
    def test_a_secret_too_short_to_be_one_refuses(
        self, monkeypatch: pytest.MonkeyPatch, secret: str
    ) -> None:
        """A passphrase somebody typed is not a key.

        Args:
            monkeypatch (pytest.MonkeyPatch): The patcher.
            secret (str): The rejected secret.
        """
        config = IntegrationConfig()
        monkeypatch.setenv(config.credential_key_env, secret)

        with pytest.raises(MTCredentialCipherKeyUnusable):
            CredentialCipher(config)

    def test_the_refusal_names_the_variable_to_fix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An operator should not have to read the source to fix it.

        Args:
            monkeypatch (pytest.MonkeyPatch): The patcher.
        """
        config = IntegrationConfig()
        monkeypatch.setenv(config.credential_key_env, "short")

        with pytest.raises(MTCredentialCipherKeyUnusable) as raised:
            CredentialCipher(config)

        assert config.credential_key_env in str(raised.value)

    def test_the_refusal_does_not_quote_the_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Short is not the same as unimportant.

        Args:
            monkeypatch (pytest.MonkeyPatch): The patcher.
        """
        config = IntegrationConfig()
        monkeypatch.setenv(config.credential_key_env, "hunter2secret")

        with pytest.raises(MTCredentialCipherKeyUnusable) as raised:
            CredentialCipher(config)

        assert "hunter2secret" not in str(raised.value)
