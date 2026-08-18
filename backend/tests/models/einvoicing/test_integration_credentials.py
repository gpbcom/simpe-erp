from __future__ import annotations

# Third-party imports
import pytest

# First-party imports
from models.integrations.exceptions import (
    MTIntegrationCredentialsInvalidAccountId,
    MTIntegrationCredentialsInvalidApiKey,
    MTIntegrationCredentialsInvalidBaseUrl,
    MTIntegrationCredentialsInvalidLegalEntityId,
)
from models.integrations.integration_credentials import IntegrationCredentials
from tests.annotations import ModelInput

KEY = "sk_live_0123456789abcdef"


class TestHoldingACredential:
    """Tests for the value a connector authenticates with."""

    def test_a_key_is_enough(self) -> None:
        """Two of the four platforms want nothing else."""
        credentials = IntegrationCredentials(api_key=KEY)

        assert credentials.api_key == KEY
        assert credentials.account_id is None
        assert credentials.legal_entity_id is None

    def test_it_carries_the_references_a_platform_routes_on(self) -> None:
        """B2Brouter puts an account in the path; Storecove wants an entity."""
        credentials = IntegrationCredentials(
            api_key=KEY, account_id="12345", legal_entity_id="98765"
        )

        assert credentials.account_id == "12345"
        assert credentials.legal_entity_id == "98765"

    def test_whitespace_is_trimmed(self) -> None:
        """A key is pasted, and a paste brings whitespace with it."""
        credentials = IntegrationCredentials(api_key=f"  {KEY}  ")

        assert credentials.api_key == KEY

    def test_it_is_frozen(self) -> None:
        """A credential is read, never edited in place."""
        credentials = IntegrationCredentials(api_key=KEY)

        with pytest.raises(Exception):
            credentials.api_key = "other"

    def test_unknown_fields_are_refused(self) -> None:
        """Extras are forbidden.

        Notes:
            A typo'd field name on a secret-bearing model would be silently
            dropped and the connector would authenticate with less than the
            caller believed it had sent.
        """
        with pytest.raises(Exception):
            IntegrationCredentials(api_key=KEY, api_secret="x")


class TestRefusingAnUnusableCredential:
    """Tests for the values that could not authenticate."""

    @pytest.mark.parametrize("value", ["", "   ", None, 42, ["k"]])
    def test_a_missing_key_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected key.
        """
        with pytest.raises(MTIntegrationCredentialsInvalidApiKey):
            IntegrationCredentials(api_key=value)

    def test_a_key_too_short_to_be_one_is_refused(self) -> None:
        """A two-character key is a paste that went wrong.

        Notes:
            Caught here rather than by the platform's 401, which costs a round
            trip and reports the failure a step away from the typo.
        """
        with pytest.raises(MTIntegrationCredentialsInvalidApiKey):
            IntegrationCredentials(api_key="ab")

    def test_a_key_longer_than_any_platform_issues_is_refused(self) -> None:
        """The ceiling stops a whole file being pasted into the field."""
        with pytest.raises(MTIntegrationCredentialsInvalidApiKey):
            IntegrationCredentials(api_key="k" * 513)

    def test_the_refusal_never_quotes_the_secret(self) -> None:
        """**The reason this validator is written differently from every other.**

        Notes:
            Every other validator here reports the value it refused, which is
            what makes a 422 actionable. This one must not: the refused value is
            the secret, and the message reaches the application log.
        """
        secret = "s" * 600
        with pytest.raises(MTIntegrationCredentialsInvalidApiKey) as raised:
            IntegrationCredentials(api_key=secret)

        assert secret not in str(raised.value)

    @pytest.mark.parametrize("value", ["", "   ", 7, ["a"]])
    def test_an_unusable_account_id_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected account reference.
        """
        with pytest.raises(MTIntegrationCredentialsInvalidAccountId):
            IntegrationCredentials(api_key=KEY, account_id=value)

    def test_an_over_long_account_id_is_refused(self) -> None:
        """A reference is an identifier, not a document."""
        with pytest.raises(MTIntegrationCredentialsInvalidAccountId):
            IntegrationCredentials(api_key=KEY, account_id="a" * 129)

    @pytest.mark.parametrize("value", ["", "   ", 7])
    def test_an_unusable_legal_entity_id_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected legal-entity reference.
        """
        with pytest.raises(MTIntegrationCredentialsInvalidLegalEntityId):
            IntegrationCredentials(api_key=KEY, legal_entity_id=value)

    def test_an_over_long_legal_entity_id_is_refused(self) -> None:
        """Bounded for the same reason the account reference is."""
        with pytest.raises(MTIntegrationCredentialsInvalidLegalEntityId):
            IntegrationCredentials(api_key=KEY, legal_entity_id="e" * 129)


class TestTheBaseUrl:
    """Tests for the address a sandbox is reached at."""

    def test_an_https_address_is_accepted(self) -> None:
        """Pointing at a sandbox must not need a release."""
        credentials = IntegrationCredentials(
            api_key=KEY, base_url="https://api-staging.b2brouter.net"
        )

        assert credentials.base_url == "https://api-staging.b2brouter.net"

    def test_the_trailing_slash_is_dropped(self) -> None:
        """So a connector can join paths without each one guessing."""
        credentials = IntegrationCredentials(
            api_key=KEY, base_url="https://api.storecove.com/"
        )

        assert credentials.base_url == "https://api.storecove.com"

    def test_plain_http_is_refused_rather_than_upgraded(self) -> None:
        """**Refused, not rewritten.**

        Notes:
            Every request made with this address carries the API key. Quietly
            promoting the scheme is how an operator comes to believe they are
            talking to a host they are not.
        """
        with pytest.raises(MTIntegrationCredentialsInvalidBaseUrl):
            IntegrationCredentials(api_key=KEY, base_url="http://api.example.com")

    @pytest.mark.parametrize("value", ["", "   ", "api.example.com", 42])
    def test_an_address_that_is_not_absolute_https_is_refused(
        self, value: ModelInput
    ) -> None:
        """Args:
        value (ModelInput): The rejected address.
        """
        with pytest.raises(MTIntegrationCredentialsInvalidBaseUrl):
            IntegrationCredentials(api_key=KEY, base_url=value)


class TestKeepingTheSecretOutOfTheLogs:
    """Tests for the two representations that would otherwise leak it.

    Notes:
        Pydantic's default ``__repr__`` prints every field, so a secret on an
        ordinary model reaches the log the first time anything formats it — a
        debug line, a traceback frame, an exception's own arguments. These are
        the paths that do not go through ``model_dump``.
    """

    def test_repr_carries_no_secret(self) -> None:
        """What a traceback frame prints."""
        credentials = IntegrationCredentials(api_key=KEY)

        assert KEY not in repr(credentials)

    def test_str_carries_no_secret(self) -> None:
        """What an f-string in a log line prints."""
        credentials = IntegrationCredentials(api_key=KEY)

        assert KEY not in f"{credentials}"

    def test_a_formatted_container_carries_no_secret(self) -> None:
        """The realistic case: it is logged inside something else.

        Notes:
            A list or dict formats its members with ``repr``, so this is the
            path a credential most plausibly takes into a log — never on its
            own, always as part of some state being dumped.
        """
        credentials = IntegrationCredentials(api_key=KEY)

        assert KEY not in repr({"credentials": credentials})
        assert KEY not in repr([credentials])

    def test_the_hint_shows_only_the_tail(self) -> None:
        """Enough to recognise your own key, useless to anybody else."""
        credentials = IntegrationCredentials(api_key=KEY)

        hint = credentials.hint()

        assert hint == "…cdef"
        assert KEY not in hint

    def test_the_hint_is_short_enough_for_the_stored_bound(self) -> None:
        """It is persisted in a field that refuses anything key-sized.

        Notes:
            The two bounds are in different classes and must agree. This is
            where they are checked against each other.
        """
        credentials = IntegrationCredentials(api_key="k" * 512)

        assert len(credentials.hint()) <= 16
