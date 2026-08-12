from __future__ import annotations

# Standard library imports
from datetime import date, datetime, timezone
from decimal import Decimal

# Third-party imports
import pytest

# First-party imports
from models.enums import BillingPeriodicity, Language
from models.settings.billing_settings import BillingSettings
from models.settings.exceptions import (
    MTBillingSettingsInvalidDate,
    MTBillingSettingsInvalidId,
    MTBillingSettingsInvalidIndemnity,
    MTBillingSettingsInvalidPaymentTerms,
    MTBillingSettingsInvalidPenaltyMultiplier,
    MTBillingSettingsInvalidPeriodicity,
    MTBillingSettingsInvalidUpdatedBy,
)
from tests.annotations import ModelInput


class TestBillingSettingsSingleton:
    """Tests for the one row these rules live in."""

    def test_the_defaults_are_usable_without_any_input(self) -> None:
        """The seeded row is what an agency invoices under until it says otherwise.

        Notes:
            Every default is also what a French home-care invoice ordinarily
            carries, so a deployment nobody has configured still produces a
            conforming document.
        """
        settings = BillingSettings()
        assert settings.id == BillingSettings.SINGLETON_ID
        assert settings.periodicity is BillingPeriodicity.MONTHLY
        assert settings.payment_terms_days == 30
        assert settings.late_penalty_multiplier == 3
        assert settings.recovery_indemnity_eur == Decimal("40.00")
        assert settings.escompte_offered is False

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("other-settings", id="Invalid - another identifier"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_a_second_row_cannot_be_invented(self, value: ModelInput) -> None:
        """There is nowhere for a second set of invoicing rules to live.

        Notes:
            Refusing any other identifier is what keeps the table to one row
            even when a caller makes one up — otherwise the question "which
            terms was this invoice issued under?" has no answer the document can
            settle afterwards.
        """
        with pytest.raises(MTBillingSettingsInvalidId):
            BillingSettings(id=value)


class TestBillingSettingsTerms:
    """Tests for the commercial terms printed on every invoice."""

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0, id="Invalid - zero days"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(90, id="Invalid - above the statutory ceiling"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param("30", id="Invalid - string"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_payment_terms_stay_inside_the_legal_range(self, value: ModelInput) -> None:
        """The ceiling is statutory, not a preference.

        Notes:
            The code de commerce caps agreed terms, so a longer one would print
            an obligation the agency could not enforce if it ever had to.
        """
        with pytest.raises(MTBillingSettingsInvalidPaymentTerms):
            BillingSettings(payment_terms_days=value)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(BillingSettings.MIN_PAYMENT_TERMS_DAYS, id="the floor"),
            pytest.param(BillingSettings.MAX_PAYMENT_TERMS_DAYS, id="the ceiling"),
        ],
    )
    def test_both_ends_of_the_range_are_accepted(self, value: int) -> None:
        """The bounds are inclusive, so the statutory maximum is allowed."""
        assert BillingSettings(payment_terms_days=value).payment_terms_days == value

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0, id="Invalid - below the legal rate"),
            pytest.param(11, id="Invalid - above the accepted range"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_the_penalty_multiplier_stays_in_range(self, value: ModelInput) -> None:
        """A penalty below the legal interest rate is not a penalty."""
        with pytest.raises(MTBillingSettingsInvalidPenaltyMultiplier):
            BillingSettings(late_penalty_multiplier=value)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(Decimal("-1"), id="Invalid - negative"),
            pytest.param(Decimal("1001"), id="Invalid - implausibly large"),
            pytest.param("not an amount", id="Invalid - unparseable"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_unusable_indemnity_is_refused(self, value: ModelInput) -> None:
        """The recovery indemnity is money, and money has a shape."""
        with pytest.raises(MTBillingSettingsInvalidIndemnity):
            BillingSettings(recovery_indemnity_eur=value)

    def test_the_indemnity_is_rounded_to_the_cent(self) -> None:
        """An amount printed on an invoice never carries a third decimal."""
        assert BillingSettings(
            recovery_indemnity_eur=40
        ).recovery_indemnity_eur == Decimal("40.00")

    def test_the_indemnity_keeps_a_float_exact(self) -> None:
        """Money is routed through ``str`` so binary rounding never enters."""
        assert BillingSettings(
            recovery_indemnity_eur=41.55
        ).recovery_indemnity_eur == Decimal("41.55")

    def test_an_unknown_periodicity_is_refused(self) -> None:
        """A rule the application cannot resolve a window from is unusable."""
        with pytest.raises(MTBillingSettingsInvalidPeriodicity):
            BillingSettings(periodicity="fortnightly")

    def test_a_missing_periodicity_falls_back_to_monthly(self) -> None:
        """Monthly is what an agency invoices on unless it says otherwise."""
        assert (
            BillingSettings(periodicity=None).periodicity is BillingPeriodicity.MONTHLY
        )


class TestBillingSettingsAudit:
    """Tests for the record of who changed the terms."""

    def test_the_editor_is_optional_but_never_blank(self) -> None:
        """Seeded defaults were nobody's decision; an edit is somebody's.

        Notes:
            "Who put the payment terms to sixty days?" is a question with a name
            attached, and a blank string is that name silently absent.
        """
        assert BillingSettings(updated_by=None).updated_by is None
        with pytest.raises(MTBillingSettingsInvalidUpdatedBy):
            BillingSettings(updated_by="   ")

    def test_a_timestamp_is_read_from_an_iso_string(self) -> None:
        """Stored rows come back as strings and must parse without a caller."""
        settings = BillingSettings(updated_at="2026-04-01T09:30:00+00:00")
        assert settings.updated_at == datetime(2026, 4, 1, 9, 30, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("not a date", id="Invalid - unparseable"),
            pytest.param(20260401, id="Invalid - int"),
        ],
    )
    def test_an_unusable_timestamp_is_refused(self, value: ModelInput) -> None:
        """Only a datetime or an ISO string records when the rules moved."""
        with pytest.raises(MTBillingSettingsInvalidDate):
            BillingSettings(updated_at=value)


class TestBillingSettingsBehaviour:
    """Tests for what the rules are actually asked to work out."""

    def test_the_due_date_counts_from_the_invoice_date(self) -> None:
        """The terms say "within thirty days", and that is what is printed.

        Notes:
            Counted from the invoice date rather than from the end of the period
            billed, which is what the customer reads. Computed here so the due
            date on the document and the one in the record cannot differ.
        """
        settings = BillingSettings(payment_terms_days=30)
        assert settings.due_date_for(date(2026, 4, 1)) == date(2026, 5, 1)

    def test_the_window_comes_from_the_configured_rule(self) -> None:
        """A caller holding the settings never reaches past them."""
        weekly = BillingSettings(periodicity=BillingPeriodicity.WEEKLY)
        assert weekly.window_for(date(2026, 8, 13)) == (
            date(2026, 8, 10),
            date(2026, 8, 16),
        )
        assert weekly.previous_window(date(2026, 8, 13)) == (
            date(2026, 8, 3),
            date(2026, 8, 9),
        )

    @pytest.mark.parametrize(
        ("offered", "language", "expected"),
        [
            pytest.param(False, Language.FR, "néant", id="no discount, French"),
            pytest.param(True, Language.FR, "accordé", id="a discount, French"),
            pytest.param(False, Language.EN, "none", id="no discount, English"),
            pytest.param(True, Language.EN, "offered", id="a discount, English"),
        ],
    )
    def test_the_discount_is_always_stated(
        self, offered: bool, language: Language, expected: str
    ) -> None:
        """Saying nothing about the escompte is itself a non-conformity.

        Notes:
            The flag decides *which* sentence is printed and never whether one
            is, which is why there is no branch that omits it.
        """
        sentence = BillingSettings(escompte_offered=offered).describe_terms(language)
        assert expected in sentence

    def test_the_terms_sentence_names_the_number_of_days(self) -> None:
        """A term nobody can read off the invoice is not a term."""
        assert "45" in BillingSettings(payment_terms_days=45).describe_terms()

    def test_french_is_the_default_language(self) -> None:
        """This is a French agency invoicing French customers."""
        assert "Paiement" in BillingSettings().describe_terms()
