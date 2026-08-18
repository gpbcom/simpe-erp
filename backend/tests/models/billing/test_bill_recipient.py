from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import Dict

# Third-party imports
import pytest

# First-party imports
from models.billing.bill_recipient import BillRecipient
from models.billing.exceptions import (
    MTBillRecipientInvalidAddress,
    MTBillRecipientInvalidKind,
    MTBillRecipientInvalidName,
    MTBillRecipientInvalidServiceCode,
    MTBillRecipientInvalidShare,
    MTBillRecipientInvalidSiren,
    MTBillRecipientInvalidVatNumber,
    MTBillRecipientMissingSiren,
    MTBillRecipientUnexpectedSiren,
    MTInvalidBillRecipientException,
)
from models.enums import RecipientKind
from models.geo.postal_address import PostalAddress
from tests.annotations import ModelInput

ADDRESS = PostalAddress(
    street="1 rue des Lilas",
    postal_code="75011",
    city="Paris",
    country="France",
    latitude=48.85,
    longitude=2.35,
)

#: A SIREN whose Luhn check digit is correct.
VALID_SIREN = "130025265"


@pytest.fixture
def household() -> Dict[str, ModelInput]:
    """Return the arguments for a private individual.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    return {"name": "Jeanne Vincent", "address": ADDRESS}


class TestBillRecipient:
    """Tests for the party that owes an invoice."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_recipient_is_a_private_individual_by_default(
        self, household: Dict[str, ModelInput]
    ) -> None:
        """**The safe default, and the ordinary one.**

        Notes:
            An individual is *reported* rather than *transmitted*, so a missing
            kind cannot cause a document to be sent to a platform for a party
            nobody identified.
        """
        recipient = BillRecipient(**household)

        assert recipient.kind is RecipientKind.INDIVIDUAL
        assert recipient.is_individual() is True
        assert recipient.legal_identifier() is None

    def test_a_public_body_carries_its_routing_code(self) -> None:
        """A public body is reached at a service inside it, not as a whole."""
        recipient = BillRecipient(
            kind=RecipientKind.PUBLIC,
            name="Conseil départemental de Paris",
            address=ADDRESS,
            siren=VALID_SIREN,
            service_code="APA",
        )

        assert recipient.service_code == "APA"
        assert recipient.legal_identifier() == VALID_SIREN
        assert recipient.is_individual() is False

    # ------------------------------------------------------------------ #
    #  The legal identifier
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("130 025 265", id="Spaced, as it is on a letterhead"),
            pytest.param("130-025-265", id="Hyphenated"),
        ],
    )
    def test_a_siren_is_read_however_it_was_typed(self, value: str) -> None:
        """Separators vary by who is reading the letterhead."""
        recipient = BillRecipient(
            kind=RecipientKind.BUSINESS,
            name="Mutuelle du Centre",
            address=ADDRESS,
            siren=value,
        )

        assert recipient.siren == VALID_SIREN

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("13002526", id="Invalid - eight digits"),
            pytest.param("1300252650", id="Invalid - ten digits"),
            pytest.param("13002526A", id="Invalid - not all digits"),
            pytest.param("130025256", id="Invalid - two figures transposed"),
        ],
    )
    def test_a_malformed_siren_is_refused(self, value: str) -> None:
        """**The check digit is the point, not the length.**

        Notes:
            Nine digits is a shape. The Luhn checksum is what catches the
            transposed pair. Caught here it is a 422 naming the field; missed,
            it is a platform refusing an invoice whose number cannot be reused.
        """
        with pytest.raises(MTBillRecipientInvalidSiren):
            BillRecipient(
                kind=RecipientKind.BUSINESS,
                name="Mutuelle du Centre",
                address=ADDRESS,
                siren=value,
            )

    def test_a_professional_without_a_siren_is_refused(self) -> None:
        """A business cannot be routed to without one, so it is not optional."""
        with pytest.raises(MTBillRecipientMissingSiren):
            BillRecipient(
                kind=RecipientKind.BUSINESS,
                name="Mutuelle du Centre",
                address=ADDRESS,
            )

    def test_a_household_with_a_siren_is_refused(
        self, household: Dict[str, ModelInput]
    ) -> None:
        """**The other direction is an error too.**

        Notes:
            A household carrying a legal identifier would be read as a company
            by every downstream system, and the invoice would be transmitted for
            delivery to a party that does not exist.
        """
        with pytest.raises(MTBillRecipientUnexpectedSiren):
            BillRecipient(**{**household, "siren": VALID_SIREN})

    # ------------------------------------------------------------------ #
    #  The other identifiers
    # ------------------------------------------------------------------ #

    def test_a_vat_number_is_normalised(self) -> None:
        """Spacing and case vary. The number does not."""
        recipient = BillRecipient(
            kind=RecipientKind.BUSINESS,
            name="Mutuelle du Centre",
            address=ADDRESS,
            siren=VALID_SIREN,
            vat_number="fr 12 345678900",
        )

        assert recipient.vat_number == "FR12345678900"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("FR/1234", id="Invalid - not alphanumeric"),
            pytest.param("F" * 21, id="Invalid - too long"),
        ],
    )
    def test_a_malformed_vat_number_is_refused(self, value: str) -> None:
        """Shape only: the member states do not agree on a format."""
        with pytest.raises(MTBillRecipientInvalidVatNumber):
            BillRecipient(
                kind=RecipientKind.BUSINESS,
                name="Mutuelle",
                address=ADDRESS,
                siren=VALID_SIREN,
                vat_number=value,
            )

    def test_a_service_code_outside_a_public_body_is_refused(self) -> None:
        """**Refused rather than dropped on the way out.**

        Notes:
            A code silently ignored is one whoever entered it goes on believing
            the invoice is routed by.
        """
        with pytest.raises(MTBillRecipientInvalidServiceCode):
            BillRecipient(
                kind=RecipientKind.BUSINESS,
                name="Mutuelle",
                address=ADDRESS,
                siren=VALID_SIREN,
                service_code="APA",
            )

    # ------------------------------------------------------------------ #
    #  The funded share
    # ------------------------------------------------------------------ #

    def test_an_unset_share_means_the_whole_invoice(
        self, household: Dict[str, ModelInput]
    ) -> None:
        """Which is what a single payer owes, and therefore most invoices."""
        recipient = BillRecipient(**household)

        assert recipient.share_ttc is None
        assert recipient.owes(Decimal("124.75")) == Decimal("124.75")

    def test_a_share_is_what_that_party_owes(self) -> None:
        """The funded case: the payer's part, not the invoice total."""
        recipient = BillRecipient(
            kind=RecipientKind.PUBLIC,
            name="Conseil départemental",
            address=ADDRESS,
            siren=VALID_SIREN,
            share_ttc="80.00",
        )

        assert recipient.owes(Decimal("124.75")) == Decimal("80.00")

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("0.00", id="Invalid - a party owing nothing"),
            pytest.param("-5.00", id="Invalid - negative"),
            pytest.param("not a number", id="Invalid - unreadable"),
        ],
    )
    def test_an_unusable_share_is_refused(
        self, household: Dict[str, ModelInput], value: str
    ) -> None:
        """Zero included: a party owing nothing is not a recipient."""
        with pytest.raises(MTBillRecipientInvalidShare):
            BillRecipient(**{**household, "share_ttc": value})

    # ------------------------------------------------------------------ #
    #  The rest of the record
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - missing"),
            pytest.param("x" * 256, id="Invalid - too long"),
        ],
    )
    def test_an_unnamed_recipient_is_refused(self, value: ModelInput) -> None:
        """An invoice with no addressee is not an invoice."""
        with pytest.raises(MTBillRecipientInvalidName):
            BillRecipient(name=value, address=ADDRESS)

    def test_an_address_that_is_not_one_is_refused(self) -> None:
        """A string is not an address, however much it looks like one."""
        with pytest.raises(MTBillRecipientInvalidAddress):
            BillRecipient(name="Jeanne Vincent", address="1 rue des Lilas, Paris")

    def test_an_unknown_kind_is_refused(self, household: Dict[str, ModelInput]) -> None:
        """The kind decides the regime, so it is refused rather than defaulted."""
        with pytest.raises(MTBillRecipientInvalidKind):
            BillRecipient(**{**household, "kind": "charity"})

    # ------------------------------------------------------------------ #
    #  Exception hierarchy and serialization
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTBillRecipientInvalidAddress,
            MTBillRecipientInvalidKind,
            MTBillRecipientInvalidName,
            MTBillRecipientInvalidServiceCode,
            MTBillRecipientInvalidShare,
            MTBillRecipientInvalidSiren,
            MTBillRecipientInvalidVatNumber,
            MTBillRecipientMissingSiren,
            MTBillRecipientUnexpectedSiren,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the family the API maps."""
        assert issubclass(exception_class, MTInvalidBillRecipientException)

    def test_model_dump_round_trip(self, household: Dict[str, ModelInput]) -> None:
        """A recipient survives a dump-and-rebuild unchanged."""
        recipient = BillRecipient(**household)

        assert BillRecipient(**recipient.model_dump()) == recipient
