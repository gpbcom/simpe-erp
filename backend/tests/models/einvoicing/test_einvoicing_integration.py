from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime

# Third-party imports
import pytest

# First-party imports
from models.enums import EInvoicingProvider
from models.integrations.einvoicing_integration import EInvoicingIntegration
from models.integrations.exceptions import (
    MTEInvoicingIntegrationInvalidCiphertext,
    MTEInvoicingIntegrationInvalidCompany,
    MTEInvoicingIntegrationInvalidDate,
    MTEInvoicingIntegrationInvalidEnabled,
    MTEInvoicingIntegrationInvalidError,
    MTEInvoicingIntegrationInvalidHint,
    MTEInvoicingIntegrationInvalidId,
    MTEInvoicingIntegrationInvalidProvider,
)
from tests.annotations import ModelInput


def _integration(**overrides: ModelInput) -> EInvoicingIntegration:
    """Build an integration with sensible defaults.

    Args:
        **overrides (ModelInput): Fields to replace.

    Returns:
        EInvoicingIntegration: The record.
    """
    fields = {
        "id": "integration-1",
        "company_id": "company-1",
        "provider": EInvoicingProvider.B2BROUTER,
        "enabled": True,
        "credential_ciphertext": "gAAAAAB-ciphertext",
        "credential_hint": "…cdef",
    }
    fields.update(overrides)
    return EInvoicingIntegration(**fields)


class TestConfiguringAPlatform:
    """Tests for the record of an agency's contract with a platform."""

    def test_it_carries_the_platform_and_its_encrypted_credentials(self) -> None:
        """The three facts a transmission needs."""
        integration = _integration()

        assert integration.provider is EInvoicingProvider.B2BROUTER
        assert integration.credential_ciphertext == "gAAAAAB-ciphertext"
        assert integration.enabled is True

    def test_it_is_off_until_somebody_turns_it_on(self) -> None:
        """Holding a key is not the same as transmitting through it."""
        integration = _integration(enabled=None)

        assert integration.enabled is False

    def test_a_provider_is_accepted_as_its_value(self) -> None:
        """Rows come back from the database as strings."""
        integration = _integration(provider="storecove")

        assert integration.provider is EInvoicingProvider.STORECOVE

    def test_whitespace_is_trimmed_from_the_identifiers(self) -> None:
        """Identifiers are compared, so a stray space is a different row."""
        integration = _integration(id="  integration-1  ", company_id="  company-1  ")

        assert integration.id == "integration-1"
        assert integration.company_id == "company-1"


class TestRefusingAnUnusableIntegration:
    """Tests for the values that would make a record dangerous or meaningless."""

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_a_missing_identifier_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected identifier.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidId):
            _integration(id=value)

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_an_integration_belonging_to_nobody_is_refused(
        self, value: ModelInput
    ) -> None:
        """**The multi-tenancy guard.**

        Args:
            value (ModelInput): The rejected agency identifier.

        Notes:
            An integration with no agency would be readable by every tenant,
            and it holds the credentials of an account somebody pays for.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidCompany):
            _integration(company_id=value)

    @pytest.mark.parametrize("value", [None, "", "chorus", 7])
    def test_an_unknown_platform_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected platform.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidProvider):
            _integration(provider=value)

    @pytest.mark.parametrize("value", ["true", "false", 1, 0, []])
    def test_a_non_boolean_enabled_is_refused(self, value: ModelInput) -> None:
        """**A truthy string is the dangerous case.**

        Args:
            value (ModelInput): The rejected flag.

        Notes:
            ``"false"`` is truthy. Coercing it would transmit an agency's
            invoices on the strength of a typo, so the flag is refused rather
            than interpreted.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidEnabled):
            _integration(enabled=value)

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_missing_credentials_are_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected ciphertext.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidCiphertext):
            _integration(credential_ciphertext=value)

    def test_a_hint_long_enough_to_hold_a_key_is_refused(self) -> None:
        """**The bound is the whole point of the field.**

        Notes:
            The hint is the one part of a credential that leaves the backend. A
            field long enough to carry the key would quietly undo the reason the
            ciphertext is withheld from every response.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidHint):
            _integration(credential_hint="sk_live_0123456789abcdef")

    def test_a_hint_that_is_not_text_is_refused(self) -> None:
        """Tolerating an absent hint is not tolerating any value."""
        with pytest.raises(MTEInvoicingIntegrationInvalidHint):
            _integration(credential_hint=42)

    def test_an_absent_hint_is_tolerated(self) -> None:
        """A row written before a key was re-entered has none."""
        integration = _integration(credential_hint=None)

        assert integration.credential_hint == ""

    @pytest.mark.parametrize("value", ["", "   ", 42])
    def test_an_unusable_editor_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected account identifier.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidError):
            _integration(updated_by=value)

    @pytest.mark.parametrize("value", ["not-a-date", 20260801, ["2026-08-01"]])
    def test_a_timestamp_that_is_not_one_is_refused(self, value: ModelInput) -> None:
        """Args:
        value (ModelInput): The rejected timestamp.
        """
        with pytest.raises(MTEInvoicingIntegrationInvalidDate):
            _integration(last_checked_at=value)

    def test_an_iso_timestamp_is_accepted(self) -> None:
        """Rows come back from JSON as strings."""
        integration = _integration(last_checked_at="2026-08-11T09:00:00+00:00")

        assert integration.last_checked_at == datetime(2026, 8, 11, 9, 0, tzinfo=UTC)


class TestRecordingWhyACheckFailed:
    """Tests for the field written from a third party's error response."""

    def test_a_failure_is_kept(self) -> None:
        """So a manager can be told what the platform said."""
        integration = _integration(last_check_error="401 Unauthorized")

        assert integration.last_check_error == "401 Unauthorized"

    def test_an_over_long_failure_is_truncated_rather_than_refused(self) -> None:
        """**Truncated, because nobody here controls the length.**

        Notes:
            This is written from a platform's own error body. A row that could
            not be saved because a third party was verbose would lose the very
            diagnosis it was trying to keep.
        """
        integration = _integration(last_check_error="e" * 900)

        assert len(integration.last_check_error) == 512

    def test_a_blank_failure_reads_as_no_failure(self) -> None:
        """An empty string is not a diagnosis."""
        integration = _integration(last_check_error="   ")

        assert integration.last_check_error is None

    def test_a_failure_that_is_not_text_is_refused(self) -> None:
        """Tolerating verbosity is not tolerating any value."""
        with pytest.raises(MTEInvoicingIntegrationInvalidError):
            _integration(last_check_error={"code": 401})


class TestDecidingWhetherToTransmit:
    """Tests for the question the transmission service actually asks.

    Notes:
        ``enabled`` and ``last_check_error`` are two different facts, and
        ``is_usable`` is where they meet. Disabling is a manager's decision and
        survives; a failed check is a fact about the last attempt that the next
        one may overturn.
    """

    def test_an_enabled_healthy_integration_is_usable(self) -> None:
        """The ordinary case."""
        assert _integration().is_usable() is True

    def test_a_disabled_integration_is_not_usable(self) -> None:
        """Holding a working key is not consent to transmit."""
        assert _integration(enabled=False).is_usable() is False

    def test_an_integration_whose_last_check_failed_is_not_usable(self) -> None:
        """**Stops an invoice going to a platform that answered 401.**"""
        assert _integration(last_check_error="401").is_usable() is False

    def test_a_failed_check_does_not_disable_it(self) -> None:
        """The distinction the two fields exist for.

        Notes:
            A key rotated at the platform must not silently un-choose the
            platform: the agency still has a contract, and the next successful
            check must restore transmission without anybody re-enabling it.
        """
        integration = _integration(last_check_error="401")

        assert integration.enabled is True
        assert integration.is_usable() is False


class TestRoundTrippingTheRecord:
    """Tests that the record survives storage."""

    def test_it_serialises_and_reloads_unchanged(self) -> None:
        """What goes into the row comes back out of it."""
        integration = _integration(
            updated_at=datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
            updated_by="nathalie@simple-erp.fr",
        )

        restored = EInvoicingIntegration.model_validate(
            integration.model_dump(mode="json")
        )

        assert restored == integration
