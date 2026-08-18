from __future__ import annotations

# Third-party imports
import pytest

# First-party imports
from models.enums import EInvoicingProvider, TransmissionKind
from models.integrations.exceptions import (
    MTProviderDescriptorInvalidCoverage,
    MTProviderDescriptorInvalidFields,
    MTProviderDescriptorInvalidName,
    MTProviderDescriptorInvalidProvider,
    MTProviderDescriptorInvalidUrl,
    MTProviderDescriptorInvalidVerified,
)
from models.integrations.provider_descriptor import ProviderDescriptor
from tests.annotations import ModelInput


def _descriptor(**overrides: ModelInput) -> ProviderDescriptor:
    """Build a descriptor with sensible defaults.

    Args:
        **overrides (ModelInput): Fields to replace.

    Returns:
        ProviderDescriptor: The entry.
    """
    fields = {
        "provider": EInvoicingProvider.INVOPOP,
        "name": "Invopop",
        "home_url": "https://www.invopop.com/",
        "documentation_url": "https://docs.invopop.com/",
        "coverage": (TransmissionKind.INVOICE,),
    }
    fields.update(overrides)
    return ProviderDescriptor(**fields)


class TestDescribingAPlatform:
    """Tests for what the gallery and the dialog read off a descriptor."""

    def test_it_carries_the_name_and_the_published_addresses(self) -> None:
        """A card is a name, a link and what the platform does."""
        descriptor = _descriptor()

        assert descriptor.name == "Invopop"
        assert descriptor.documentation_url == "https://docs.invopop.com/"

    def test_the_api_key_is_always_required(self) -> None:
        """Every platform authenticates on one.

        Notes:
            Added when omitted rather than demanded: a descriptor that forgot to
            say so is a typo, not a different kind of platform.
        """
        descriptor = _descriptor(required_fields=())

        assert descriptor.required_fields == ("api_key",)

    def test_extra_fields_come_after_the_key(self) -> None:
        """The dialog renders them in this order."""
        descriptor = _descriptor(required_fields=("legal_entity_id",))

        assert descriptor.required_fields == ("api_key", "legal_entity_id")

    def test_coverage_is_deduplicated_and_keeps_its_order(self) -> None:
        """Order is the order a card lists what a platform does."""
        descriptor = _descriptor(
            coverage=("chorus-pro", "invoice", "chorus-pro"),
        )

        assert descriptor.coverage == (
            TransmissionKind.CHORUS_PRO,
            TransmissionKind.INVOICE,
        )

    def test_a_platform_is_unverified_unless_it_says_otherwise(self) -> None:
        """**The safe direction for a missing claim is under-promising.**"""
        descriptor = _descriptor(documentation_verified=None)

        assert descriptor.documentation_verified is False


class TestRefusingAnUnusableDescriptor:
    """Tests for the values that would render a broken card."""

    @pytest.mark.parametrize("value", [None, "", "chorus", 7])
    def test_an_unknown_platform_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected platform.
        """
        with pytest.raises(MTProviderDescriptorInvalidProvider):
            _descriptor(provider=value)

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_a_missing_name_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected name.
        """
        with pytest.raises(MTProviderDescriptorInvalidName):
            _descriptor(name=value)

    @pytest.mark.parametrize(
        "value", ["", "docs.invopop.com", "http://docs.invopop.com", 42]
    )
    def test_an_address_that_is_not_absolute_https_is_refused(
        self, value: ModelInput
    ) -> None:
        """Args:
        value (ModelInput): The rejected address.

        Notes:
            A relative address would resolve against this application's own host
            and open a page that does not exist.
        """
        with pytest.raises(MTProviderDescriptorInvalidUrl):
            _descriptor(documentation_url=value)

    @pytest.mark.parametrize("value", [None, (), [], "invoice", 42])
    def test_a_platform_covering_nothing_is_refused(self, value: ModelInput) -> None:
        """**Empty coverage is a contradiction, not a default.**

        Args:
            value (ModelInput): The rejected coverage.

        Notes:
            Coverage decides which tab a card appears under and whether an
            invoice may be handed over, so a platform covering nothing would
            render everywhere and then refuse everything.
        """
        with pytest.raises(MTProviderDescriptorInvalidCoverage):
            _descriptor(coverage=value)

    def test_an_unknown_coverage_entry_is_refused(self) -> None:
        """A kind nobody can transmit is a typo."""
        with pytest.raises(MTProviderDescriptorInvalidCoverage):
            _descriptor(coverage=("invoice", "telepathy"))

    def test_a_credential_field_the_model_has_no_room_for_is_refused(self) -> None:
        """**Validated against the credentials model, not a list written here.**

        Notes:
            A platform declaring a field the credentials cannot hold would
            render a dialog input whose value goes nowhere.
        """
        with pytest.raises(MTProviderDescriptorInvalidFields):
            _descriptor(required_fields=("api_key", "client_secret"))

    @pytest.mark.parametrize("value", ["yes", 1, []])
    def test_a_non_boolean_verified_flag_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected flag.
        """
        with pytest.raises(MTProviderDescriptorInvalidVerified):
            _descriptor(documentation_verified=value)


class TestAskingWhatAPlatformCanDo:
    """Tests for the two questions asked before an invoice is handed over."""

    def test_it_answers_what_it_covers(self) -> None:
        """Asked before sending, not after being refused."""
        descriptor = _descriptor(coverage=(TransmissionKind.INVOICE,))

        assert descriptor.covers(TransmissionKind.INVOICE) is True
        assert descriptor.covers(TransmissionKind.CHORUS_PRO) is False

    def test_it_answers_which_credentials_the_dialog_must_ask(self) -> None:
        """This is why Storecove's dialog has two fields and Iopole's one."""
        descriptor = _descriptor(required_fields=("legal_entity_id",))

        assert descriptor.requires("legal_entity_id") is True
        assert descriptor.requires("account_id") is False
