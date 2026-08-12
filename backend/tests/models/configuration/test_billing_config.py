from __future__ import annotations

# Standard library imports
from decimal import Decimal

# Third-party imports
import pytest

# First-party imports
from models.configuration.billing_config import BillingConfig
from models.configuration.billing_webhook_config import BillingWebhookConfig
from models.configuration.exceptions import (
    MTBillingConfigInvalidIndemnity,
    MTBillingConfigInvalidPaymentTerms,
    MTBillingConfigInvalidPenaltyMultiplier,
    MTBillingConfigInvalidPeriodicity,
    MTS3ConfigInvalidInvoicePrefix,
)
from models.configuration.s3_config import S3Config
from models.configuration.webhook_config import WebhookConfig
from models.enums import BillingPeriodicity
from models.settings.billing_settings import BillingSettings
from tests.annotations import ModelInput


class TestBillingConfig:
    """Tests for the invoicing rules a deployment starts with."""

    def test_the_defaults_produce_a_conforming_invoice(self) -> None:
        """A deployment nobody configured still invoices correctly.

        Notes:
            Thirty-day terms, the legal interest rate trebled, a forty-euro
            recovery indemnity and no early-settlement discount are what a
            French home-care invoice carries; none of them is a placeholder
            somebody has to remember to change.
        """
        config = BillingConfig()
        assert config.periodicity is BillingPeriodicity.MONTHLY
        assert config.payment_terms_days == 30
        assert config.late_penalty_multiplier == 3
        assert config.recovery_indemnity_eur == Decimal("40.00")
        assert config.escompte_offered is False

    def test_the_defaults_match_the_stored_model(self) -> None:
        """The seed and the row it seeds cannot disagree.

        Notes:
            If they drifted, a deployment's first read would silently write
            rules different from the ones its configuration file states.
        """
        seeded = BillingConfig().to_settings()
        assert seeded.model_dump(exclude={"updated_by", "updated_at"}) == (
            BillingSettings().model_dump(exclude={"updated_by", "updated_at"})
        )

    def test_the_seeded_row_has_no_editor(self) -> None:
        """The defaults were nobody's decision.

        Notes:
            Attributing them to whoever happened to open the screen first would
            be a false audit trail on a record whose whole purpose is answering
            "who changed the terms?".
        """
        assert BillingConfig().to_settings().updated_by is None

    def test_the_seeded_row_is_the_singleton(self) -> None:
        """There is one set of invoicing rules, whatever seeded it."""
        assert BillingConfig().to_settings().id == BillingSettings.SINGLETON_ID

    @pytest.mark.parametrize(
        ("field", "value", "expected"),
        [
            pytest.param(
                "periodicity",
                "fortnightly",
                MTBillingConfigInvalidPeriodicity,
                id="Invalid - unknown periodicity",
            ),
            pytest.param(
                "payment_terms_days",
                90,
                MTBillingConfigInvalidPaymentTerms,
                id="Invalid - terms above the statutory ceiling",
            ),
            pytest.param(
                "payment_terms_days",
                0,
                MTBillingConfigInvalidPaymentTerms,
                id="Invalid - zero-day terms",
            ),
            pytest.param(
                "late_penalty_multiplier",
                0,
                MTBillingConfigInvalidPenaltyMultiplier,
                id="Invalid - multiplier below the legal rate",
            ),
            pytest.param(
                "recovery_indemnity_eur",
                "-1",
                MTBillingConfigInvalidIndemnity,
                id="Invalid - negative indemnity",
            ),
        ],
    )
    def test_a_bad_configuration_fails_at_start_up(
        self, field: str, value: ModelInput, expected: type
    ) -> None:
        """A wrong value in a file must not wait for the first billing run.

        Notes:
            The stored model would refuse it too, but a month later and with
            nobody watching. Checked here, the deployment refuses to start and
            names the field.
        """
        with pytest.raises(expected):
            BillingConfig(**{field: value})

    def test_a_yaml_float_keeps_its_exact_value(self) -> None:
        """Money is routed through ``str`` so binary rounding never enters."""
        assert BillingConfig(
            recovery_indemnity_eur=41.55
        ).recovery_indemnity_eur == Decimal("41.55")


class TestBillingWebhookConfig:
    """Tests for the webhook that emails a validated invoice."""

    def test_it_points_at_its_own_endpoint_with_its_own_secret(self) -> None:
        """**The reason this is a subclass rather than a second field.**

        Notes:
            Mounted as a plain ``WebhookConfig``, a deployment whose YAML lacked
            a ``billing_webhook`` block would send an invoice announcement to
            the *planning* endpoint carrying the *planning* secret — a
            misconfiguration that authenticates successfully and does the wrong
            thing.
        """
        billing = BillingWebhookConfig()
        planning = WebhookConfig()
        assert billing.url.endswith("/api/v1/webhooks/bill-accepted")
        assert billing.token_env == "BILLING_WEBHOOK_TOKEN"
        assert billing.url != planning.url
        assert billing.token_env != planning.token_env

    def test_it_is_disabled_by_default(self) -> None:
        """An agency with no outbound mail should not log a failure per bill."""
        assert BillingWebhookConfig().enabled is False

    def test_it_inherits_the_parent_validators(self) -> None:
        """No exception family of its own; a bad URL is refused as usual."""
        with pytest.raises(Exception):
            BillingWebhookConfig(url="not-a-url")


class TestInvoiceKeyPrefix:
    """Tests for where generated invoices are written."""

    def test_invoices_have_their_own_prefix(self) -> None:
        """Kept apart from the photographs and the logos, which are public."""
        config = S3Config()
        assert config.invoice_key_prefix == "invoices/"
        assert config.invoice_key_prefix != config.photo_key_prefix
        assert config.invoice_key_prefix != config.logo_key_prefix

    def test_a_prefix_configured_without_a_slash_still_groups(self) -> None:
        """The trailing slash is added rather than demanded."""
        assert S3Config(invoice_key_prefix="factures").invoice_key_prefix == (
            "factures/"
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("/invoices/", id="Invalid - leading slash"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_an_unusable_invoice_prefix_names_itself(self, value: ModelInput) -> None:
        """Each prefix raises its own exception.

        Notes:
            The API's exception-to-status map is keyed on the class, and a
            rejected invoice prefix reporting itself as a bad photo prefix would
            send whoever is fixing the deployment to the wrong line.
        """
        with pytest.raises(MTS3ConfigInvalidInvoicePrefix):
            S3Config(invoice_key_prefix=value)

    def test_a_pdf_is_still_refused_by_the_image_sniffer(self) -> None:
        """The invoice path is parallel, never a relaxation of the image one.

        Notes:
            A bucket serving attacker-chosen content types is how a stored file
            becomes a stored payload, so the accepted image types stay exactly
            three however many prefixes the bucket grows.
        """
        assert S3Config.ALLOWED_PHOTO_CONTENT_TYPES == (
            "image/jpeg",
            "image/png",
            "image/webp",
        )
