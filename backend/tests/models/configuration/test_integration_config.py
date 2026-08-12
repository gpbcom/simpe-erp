from __future__ import annotations

# Standard library imports
import pathlib

# Third-party imports
import pytest

# First-party imports
from models.configuration.app_config import AppConfig
from models.configuration.exceptions import (
    MTIntegrationConfigInvalidKeyEnv,
    MTIntegrationConfigInvalidProviders,
    MTIntegrationConfigInvalidTimeout,
    MTIntegrationConfigMissingKey,
    MTIntegrationConfigProviderUnknown,
)
from models.configuration.integration_config import IntegrationConfig
from models.enums import EInvoicingProvider, RecipientKind, TransmissionKind
from tests.annotations import ModelInput

CONF = pathlib.Path(__file__).resolve().parents[3] / "conf"
SHIPPED = CONF / "app.yaml"
#: Every configuration file a process may be pointed at. The catalogue is one
#: fact about the outside world, so all of them must state it identically.
DEPLOYED = ("app.yaml", "app.docker.yaml", "app.dev.yaml")


def _configured() -> IntegrationConfig:
    """Return the section as the shipped configuration file declares it.

    Returns:
        IntegrationConfig: The deployed catalogue, not a fixture of one.

    Notes:
        Read from ``conf/app.yaml`` on purpose. The catalogue is configuration
        now, so a test built on a hand-written fixture would keep passing after
        somebody deleted a platform from the file that actually ships.
    """
    return AppConfig.load(SHIPPED).integrations


def _entry(**overrides: ModelInput) -> dict:
    """Return a catalogue entry as it appears in the configuration file.

    Args:
        **overrides (ModelInput): Fields to replace.

    Returns:
        dict: The raw mapping.
    """
    fields = {
        "provider": "invopop",
        "name": "Invopop",
        "home_url": "https://www.invopop.com/",
        "documentation_url": "https://docs.invopop.com/",
        "coverage": ["invoice"],
    }
    fields.update(overrides)
    return fields


class TestTheDefaults:
    """Tests for what a deployment gets by configuring nothing."""

    def test_it_names_a_variable_rather_than_holding_a_key(self) -> None:
        """**The distinction that lets this section sit in the open.**

        Notes:
            The name is configuration; the value is a secret. A key written in
            ``app.yaml`` would be a key in the image and in version control.
        """
        config = IntegrationConfig()

        assert config.credential_key_env == "EINVOICING_CREDENTIAL_KEY"

    def test_the_timeout_has_a_workable_default(self) -> None:
        """A platform is a third party over the internet."""
        assert IntegrationConfig().request_timeout_seconds == 30.0

    def test_the_section_is_optional_in_the_application_configuration(self) -> None:
        """Every section carries a default, so an absent one is not an error."""
        assert AppConfig().integrations.credential_key_env

    def test_an_unconfigured_deployment_offers_no_platform(self) -> None:
        """**Accepted rather than refused, and deliberately so.**

        Notes:
            A deployment that declares no platform has not been configured yet.
            Refusing to build the object would take the whole application down
            rather than the one screen that needs it — and the gallery already
            says out loud that nothing is connected.
        """
        assert IntegrationConfig().all_providers() == ()


class TestRefusingAnUnusableSection:
    """Tests for the values that would leave a deployment unable to transmit."""

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_an_unnamed_variable_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected variable name.
        """
        with pytest.raises(MTIntegrationConfigInvalidKeyEnv):
            IntegrationConfig(credential_key_env=value)

    @pytest.mark.parametrize("value", [None, "soon", [], True])
    def test_a_timeout_that_is_not_a_number_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected timeout.
        """
        with pytest.raises(MTIntegrationConfigInvalidTimeout):
            IntegrationConfig(request_timeout_seconds=value)

    @pytest.mark.parametrize("value", [0, 0.5, 121, -1])
    def test_a_timeout_outside_the_range_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected timeout.

        Notes:
            The floor exists because a sub-second timeout fails against every
            real platform; the ceiling because one that never answers must not
            hold a worker open.
        """
        with pytest.raises(MTIntegrationConfigInvalidTimeout):
            IntegrationConfig(request_timeout_seconds=value)

    def test_a_numeric_string_is_accepted(self) -> None:
        """YAML and environment overrides both arrive as text."""
        assert (
            IntegrationConfig(request_timeout_seconds="12.5").request_timeout_seconds
            == 12.5
        )  # noqa: E501


class TestResolvingTheKey:
    """Tests for reading the secret out of the environment."""

    def test_it_returns_what_the_variable_holds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Args:
        monkeypatch (pytest.MonkeyPatch): The patcher.
        """
        config = IntegrationConfig(credential_key_env="TEST_EINVOICING_KEY")
        monkeypatch.setenv("TEST_EINVOICING_KEY", "a-secret-value")

        assert config.get_credential_key() == "a-secret-value"

    @pytest.mark.parametrize("value", [None, ""])
    def test_an_unset_or_empty_variable_raises(
        self, monkeypatch: pytest.MonkeyPatch, value: ModelInput
    ) -> None:
        """**There is deliberately no fallback key.**

        Args:
            monkeypatch (pytest.MonkeyPatch): The patcher.
            value (ModelInput): Unset, or set to nothing.

        Notes:
            A default would encrypt every agency's platform credentials with a
            value anybody reading this repository could recover — worse than
            refusing to start, because nothing about it looks wrong.
        """
        config = IntegrationConfig(credential_key_env="TEST_EINVOICING_KEY")
        if value is None:
            monkeypatch.delenv("TEST_EINVOICING_KEY", raising=False)
        else:
            monkeypatch.setenv("TEST_EINVOICING_KEY", "")

        with pytest.raises(MTIntegrationConfigMissingKey):
            config.get_credential_key()

    def test_the_failure_names_the_variable_to_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An operator should not have to read the source to fix it.

        Args:
            monkeypatch (pytest.MonkeyPatch): The patcher.
        """
        config = IntegrationConfig(credential_key_env="TEST_EINVOICING_KEY")
        monkeypatch.delenv("TEST_EINVOICING_KEY", raising=False)

        with pytest.raises(MTIntegrationConfigMissingKey) as raised:
            config.get_credential_key()

        assert "TEST_EINVOICING_KEY" in str(raised.value)


class TestTheCatalogueThisDeploymentShips:
    """Tests for the platforms ``conf/app.yaml`` actually declares."""

    def test_every_platform_with_a_connector_is_offered(self) -> None:
        """**The invariant that keeps the code and the configuration together.**

        Notes:
            A member added to the enumeration — and so to the connector factory
            — but not to ``app.yaml`` is a platform this application can talk to
            and no agency can choose. Asserted over the enumeration rather than
            over a count, so a fifth platform fails here until it is declared.
        """
        declared = {entry.provider for entry in _configured().all_providers()}

        assert declared == set(EInvoicingProvider)

    def test_it_describes_one_platform(self) -> None:
        """What the dialog reads when a card is clicked."""
        descriptor = _configured().describe_provider(EInvoicingProvider.STORECOVE)

        assert descriptor.name == "Storecove"
        assert descriptor.requires("legal_entity_id") is True

    def test_every_recipient_kind_is_reachable_by_some_platform(self) -> None:
        """An agency must be able to meet each obligation with some choice.

        Notes:
            The file could pass every other test and still leave a département's
            invoice unsendable by anybody, which is a gap in the product rather
            than in one entry.
        """
        entries = _configured().all_providers()

        for kind in RecipientKind:
            wanted = TransmissionKind.for_recipient(kind)
            assert any(entry.covers(wanted) for entry in entries), (
                f"No platform can transmit for a {kind.value} recipient."
            )

    def test_storecove_does_not_claim_chorus_pro(self) -> None:
        """**A deliberate omission, asserted so it is not tidied away.**

        Notes:
            Storecove's documentation covers French e-reporting and does not
            mention public bodies at all. Claiming the capability would route a
            département's invoice into silence, which is indistinguishable from
            success. Absent evidence, refusing is the recoverable error.
        """
        descriptor = _configured().describe_provider(EInvoicingProvider.STORECOVE)

        assert descriptor.covers(TransmissionKind.CHORUS_PRO) is False

    def test_iopole_is_marked_unverified(self) -> None:
        """**The honesty flag, asserted so a refactor cannot quietly flip it.**

        Notes:
            Iopole's documentation renders client-side and its servers return
            malformed headers, so its connector is written to documented shape
            rather than to anything confirmed. A gallery offering all four as
            equals would be lying by omission.
        """
        descriptor = _configured().describe_provider(EInvoicingProvider.IOPOLE)

        assert descriptor.documentation_verified is False


class TestRefusingAnUnusableCatalogue:
    """Tests for what a mistyped ``providers`` block must not become."""

    def test_entries_are_read_as_mappings_from_the_file(self) -> None:
        """The block arrives as YAML, not as already-built objects."""
        config = IntegrationConfig(providers=[_entry()])

        assert config.all_providers()[0].provider is EInvoicingProvider.INVOPOP

    def test_declared_order_is_kept(self) -> None:
        """It is the order the gallery shows before an agency sorts it."""
        config = IntegrationConfig(
            providers=[_entry(), _entry(provider="iopole", name="Iopole")]
        )

        assert [entry.provider.value for entry in config.all_providers()] == [
            "invopop",
            "iopole",
        ]

    def test_the_same_platform_declared_twice_is_refused(self) -> None:
        """**Refused rather than deduplicated.**

        Notes:
            Two entries for one platform means somebody edited the file and
            meant one of them. Guessing which would show a card whose
            documentation link and coverage came from different lines.
        """
        with pytest.raises(MTIntegrationConfigInvalidProviders):
            IntegrationConfig(providers=[_entry(), _entry(name="Invopop again")])

    @pytest.mark.parametrize("value", ["invopop", 42, {"provider": "invopop"}])
    def test_something_that_is_not_a_list_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected payload.
        """
        with pytest.raises(MTIntegrationConfigInvalidProviders):
            IntegrationConfig(providers=value)

    def test_an_unknown_platform_raises_rather_than_returning_nothing(self) -> None:
        """A miss is a deployment error, not a condition to handle.

        Notes:
            An ``MT*`` rather than a ``KeyError`` so the API boundary answers
            it; a built-in would reach the client as an unexplained 500.
        """
        with pytest.raises(MTIntegrationConfigProviderUnknown):
            _configured().describe_provider("nobody")

    def test_the_failure_names_what_is_configured(self) -> None:
        """An operator should not have to read the source to fix it."""
        config = IntegrationConfig(providers=[_entry()])

        with pytest.raises(MTIntegrationConfigProviderUnknown) as raised:
            config.describe_provider("iopole")

        assert "invopop" in str(raised.value)


class TestTheConfigurationFilesAgree:
    """Tests that no deployment ships a different set of platforms."""

    @pytest.mark.parametrize("name", DEPLOYED)
    def test_every_deployment_declares_the_same_catalogue(self, name: str) -> None:
        """**Triplicated data, asserted rather than trusted.**

        Args:
            name (str): The configuration file under test.

        Notes:
            The three files are near-identical by design — they differ over
            hosts and whether email is switched on — so the catalogue is written
            three times. Which platforms exist is a fact about the outside world
            rather than about an environment, and a deployment quietly offering
            three of the four would be found by an agency that could not connect
            the one it had contracted with.
        """
        deployed = AppConfig.load(CONF / name).integrations.all_providers()
        expected = AppConfig.load(SHIPPED).integrations.all_providers()

        assert deployed == expected
