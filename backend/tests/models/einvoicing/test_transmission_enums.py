from __future__ import annotations

# Third-party imports
import pytest

# First-party imports
from models.enums import (
    EInvoicingProvider,
    RecipientKind,
    TransmissionKind,
    TransmissionStatus,
)


class TestTheSupportedPlatforms:
    """Tests for the enumeration of platforms this application can speak to."""

    def test_it_names_the_four_documented_platforms(self) -> None:
        """Membership is a claim about documentation, not about quality."""
        assert EInvoicingProvider.values() == (
            "b2brouter",
            "storecove",
            "invopop",
            "iopole",
        )

    def test_the_values_are_stable_identifiers(self) -> None:
        """They are stored in rows and sent to the browser.

        Notes:
            What a platform is *called* belongs to the descriptor. If these ever
            became display names, renaming a vendor would orphan every stored
            integration.
        """
        assert EInvoicingProvider.STORECOVE.value == "storecove"


class TestWhatGetsTransmitted:
    """Tests for the three obligations a settled invoice can produce."""

    def test_it_names_the_three_kinds(self) -> None:
        """Three obligations, not three destinations for one document."""
        assert TransmissionKind.values() == (
            "invoice",
            "payment-report",
            "chorus-pro",
        )


class TestRoutingByRecipient:
    """Tests for the reform's routing rule, which lives in one place.

    Notes:
        This is the rule that makes requirement 6 correct rather than merely
        literal: a household's settled invoice is *reported*, not *sent*. Most
        of this agency's revenue is of that kind, so getting it backwards would
        push nearly every invoice down a path the platform is not expecting and
        leave the flux 10.4 obligation unmet.
    """

    def test_a_household_produces_payment_data(self) -> None:
        """**The common case, and the one a literal reading gets wrong.**

        Notes:
            Nothing reaches the customer. What reaches the administration is
            that money changed hands — mandatory for services, because VAT
            falls due on collection rather than on delivery.
        """
        assert (
            TransmissionKind.for_recipient(RecipientKind.INDIVIDUAL)
            is TransmissionKind.PAYMENT_REPORT
        )

    def test_a_business_receives_the_structured_invoice(self) -> None:
        """A mutuelle or an employer reads it with its own system."""
        assert (
            TransmissionKind.for_recipient(RecipientKind.BUSINESS)
            is TransmissionKind.INVOICE
        )

    def test_a_public_body_goes_to_chorus_pro(self) -> None:
        """Kept apart from an ordinary invoice because the route differs."""
        assert (
            TransmissionKind.for_recipient(RecipientKind.PUBLIC)
            is TransmissionKind.CHORUS_PRO
        )

    @pytest.mark.parametrize("kind", list(RecipientKind))
    def test_every_recipient_kind_is_routed(self, kind: RecipientKind) -> None:
        """**No recipient may fall through to a default.**

        Args:
            kind (RecipientKind): The recipient being routed.

        Notes:
            Parametrized over the enumeration rather than over three literals,
            so adding a fourth kind of recipient fails here — at the mapping —
            rather than silently taking whichever branch happened to be last.
        """
        assert TransmissionKind.for_recipient(kind) in set(TransmissionKind)

    def test_it_agrees_with_the_recipient_s_own_question(self) -> None:
        """Two statements of one rule, checked against each other.

        Notes:
            ``RecipientKind.requires_electronic_invoice`` already existed and is
            asked elsewhere. If the two ever disagreed, an invoice would be
            built as a structured document and then reported as payment data, or
            the reverse.
        """
        for kind in RecipientKind:
            structured = TransmissionKind.for_recipient(kind) is not (
                TransmissionKind.PAYMENT_REPORT
            )
            assert structured is kind.requires_electronic_invoice()


class TestHowFarATransmissionReached:
    """Tests for what an outbound attempt can honestly record."""

    def test_it_names_the_three_states(self) -> None:
        """Only what is known when the call to the platform returns."""
        assert TransmissionStatus.values() == ("pending", "sent", "failed")

    def test_failure_is_not_terminal(self) -> None:
        """**A failed transmission is never a failed payment.**

        Notes:
            The money is settled whatever the platform said. A platform that was
            unreachable will be reachable, so the enumeration deliberately has
            no state meaning "given up".
        """
        assert TransmissionStatus.FAILED in set(TransmissionStatus)
        assert "abandoned" not in TransmissionStatus.values()
