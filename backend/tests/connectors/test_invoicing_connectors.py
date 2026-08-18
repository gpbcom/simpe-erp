from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from typing import Dict, List, Tuple

# Third-party imports
from pydantic import JsonValue
import httpx
import pytest

# First-party imports
from integrations.factory import ConnectorFactory
from integrations.exceptions import (
    MTConnectorNotImplemented,
    MTConnectorRejected,
    MTConnectorUnauthorised,
    MTConnectorUnavailable,
    MTConnectorUnsupported,
)
from models.billing.bill import Bill
from models.enums import (
    BillingPeriodicity,
    BillStatus,
    EInvoicingProvider,
    RecipientKind,
    ServiceCategory,
    TransmissionKind,
)
from models.integrations.integration_credentials import IntegrationCredentials
from tests.annotations import ModelInput

DOCUMENT = b"<CrossIndustryInvoice/>"


def _bill(kind: RecipientKind = RecipientKind.BUSINESS) -> Bill:
    """Build an invoice addressed to a recipient of a given kind.

    Args:
        kind (RecipientKind): Who owes the money.

    Returns:
        Bill: The invoice.
    """
    recipient: Dict[str, ModelInput] = {
        "kind": kind,
        "name": "Mutuelle Saint-Martin",
        "address": {
            "street": "12 rue de la Paix",
            "postal_code": "75002",
            "city": "Paris",
            "country": "France",
            "latitude": 48.86,
            "longitude": 2.33,
        },
    }
    if kind is not RecipientKind.INDIVIDUAL:
        recipient["siren"] = "552100554"
    if kind is RecipientKind.PUBLIC:
        recipient["service_code"] = "APA-01"
    return Bill(
        id="bill-1",
        company_id="company-1",
        number="FA-2026-0001",
        sequence=1,
        sequence_year=2026,
        periodicity=BillingPeriodicity.MONTHLY,
        customer_id="customer-1",
        customer_full_name="Marie Durand",
        customer_address=recipient["address"],
        recipient=recipient,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        issued_on=date(2026, 8, 1),
        due_on=date(2026, 8, 31),
        status=BillStatus.PAID,
        # A settled invoice must have a rendered document. The model refuses
        # the combination without one, which is the same rule that stops a
        # bill being marked paid before anybody could have been sent it.
        document_key="invoices/company-1/FA-2026-0001.pdf",
        # A real line, because ``Bill`` cross-checks its totals against the sum
        # of what it charges. An invoice whose column does not add up is the
        # one thing a customer always notices.
        lines=[
            {
                "quote_line_id": "quote-line-1",
                "name": "Aide a la toilette",
                "service_category": ServiceCategory.NECESSITY,
                "service_date": date(2026, 7, 15),
                "duration_minutes": 120,
                "hourly_rate_ht": Decimal("50.00"),
                "total_ht": Decimal("100.00"),
                "vat_rate": Decimal("0.055"),
                "vat_amount": Decimal("5.50"),
                "total_ttc": Decimal("105.50"),
            }
        ],
        total_ht=Decimal("100.00"),
        total_vat=Decimal("5.50"),
        total_ttc=Decimal("105.50"),
    )


def _client(
    responses: Dict[str, Tuple[int, JsonValue]], seen: List[httpx.Request]
) -> httpx.AsyncClient:
    """Build a client answering from a recorded map of paths.

    Args:
        responses (Dict[str, Tuple[int, JsonValue]]): Path fragment to status and
            JSON body.
        seen (List[httpx.Request]): Collects every request made.

    Returns:
        httpx.AsyncClient: A client backed by a mock transport.

    Notes:
        Matching on a *fragment* rather than the whole path keeps the recorded
        map readable while still failing loudly on an unexpected call: an
        unmatched request answers 404, which the connectors classify as a
        rejection, so a typo'd endpoint fails the test rather than passing.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        for fragment, (status, body) in responses.items():
            if fragment in str(request.url):
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "no route"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def _credentials() -> IntegrationCredentials:
    """Return credentials satisfying every platform's requirements.

    Returns:
        IntegrationCredentials: The credentials.
    """
    return IntegrationCredentials(
        api_key="sk_live_0123456789abcdef",
        account_id="acct-1",
        legal_entity_id="entity-1",
    )


class TestEveryPlatformSpeaksTheSameLanguage:
    """Tests asserting the four connectors are interchangeable.

    Notes:
        The transmission service is written once against the base class, so
        what matters is not any one platform's payload but that all four
        answer with the same receipt shape. These are parametrized over the
        whole enumeration deliberately: a fifth platform fails here until it
        behaves like the others.
    """

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_key_can_be_proven(self, provider: EInvoicingProvider) -> None:
        """Every platform offers something to check credentials against.

        Args:
            provider (EInvoicingProvider): The platform.
        """
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"ok": True})}, seen)

        connector = ConnectorFactory().build(provider, _credentials(), client=client)
        await connector.check_credentials()

        assert len(seen) == 1

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_business_invoice_yields_a_sent_receipt(
        self, provider: EInvoicingProvider
    ) -> None:
        """Args:
        provider (EInvoicingProvider): The platform.
        """
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"id": "REF-1", "guid": "REF-1"})}, seen)

        connector = ConnectorFactory().build(provider, _credentials(), client=client)
        receipt = await connector.submit_invoice(_bill(), DOCUMENT)

        assert receipt.succeeded() is True
        assert receipt.kind is TransmissionKind.INVOICE
        assert receipt.provider is provider
        assert receipt.reference == "REF-1"

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_payment_declaration_yields_a_sent_receipt(
        self, provider: EInvoicingProvider
    ) -> None:
        """**The path most of this agency's revenue takes.**

        Args:
            provider (EInvoicingProvider): The platform.
        """
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"id": "REF-2", "guid": "REF-2"})}, seen)

        connector = ConnectorFactory().build(provider, _credentials(), client=client)
        receipt = await connector.report_payment(_bill(RecipientKind.INDIVIDUAL))

        assert receipt.succeeded() is True
        assert receipt.kind is TransmissionKind.PAYMENT_REPORT

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_the_key_never_appears_in_a_url(
        self, provider: EInvoicingProvider
    ) -> None:
        """**Keys belong in headers. A URL is logged by every proxy in between.**

        Args:
            provider (EInvoicingProvider): The platform.
        """
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"id": "REF-1"})}, seen)

        connector = ConnectorFactory().build(provider, _credentials(), client=client)
        await connector.submit_invoice(_bill(), DOCUMENT)

        assert seen
        for request in seen:
            assert "sk_live_0123456789abcdef" not in str(request.url)

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_sandbox_address_is_honoured(
        self, provider: EInvoicingProvider
    ) -> None:
        """Rehearsing a transmission must not need a release.

        Args:
            provider (EInvoicingProvider): The platform.
        """
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"id": "REF-1"})}, seen)
        credentials = IntegrationCredentials(
            api_key="sk_live_0123456789abcdef",
            account_id="acct-1",
            legal_entity_id="entity-1",
            base_url="https://sandbox.example.com",
        )

        connector = ConnectorFactory().build(provider, credentials, client=client)
        await connector.check_credentials()

        assert str(seen[0].url).startswith("https://sandbox.example.com")


class TestClassifyingWhatWentWrong:
    """Tests for the three-way judgement every connector shares.

    Notes:
        The classification decides what an operator is told to do: re-enter the
        key, wait, or issue a credit note. Collapsing these into one exception
        would put that judgement in a log message nobody reads.
    """

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    @pytest.mark.parametrize("status", [401, 403])
    async def test_a_refused_key_is_reported_as_such(
        self, provider: EInvoicingProvider, status: int
    ) -> None:
        """Args:
        provider (EInvoicingProvider): The platform.
        status (int): The refusing status.
        """
        client = _client({"": (status, {"error": "bad key"})}, [])

        connector = ConnectorFactory().build(provider, _credentials(), client=client)

        with pytest.raises(MTConnectorUnauthorised):
            await connector.check_credentials()

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_platform_fault_is_retryable(
        self, provider: EInvoicingProvider
    ) -> None:
        """A 5xx is somebody else's problem, and it will pass.

        Args:
            provider (EInvoicingProvider): The platform.
        """
        client = _client({"": (503, {"error": "down"})}, [])

        connector = ConnectorFactory().build(provider, _credentials(), client=client)

        with pytest.raises(MTConnectorUnavailable):
            await connector.check_credentials()

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_refused_document_is_not_retryable(
        self, provider: EInvoicingProvider
    ) -> None:
        """**The expensive failure.**

        Args:
            provider (EInvoicingProvider): The platform.

        Notes:
            A rejected invoice has already consumed a number from a series that
            cannot have gaps, so it cannot be edited and re-sent. Reporting it
            as a transient fault would have somebody retrying a document that
            will be refused every time.
        """
        client = _client({"": (422, {"error": "malformed"})}, [])

        connector = ConnectorFactory().build(provider, _credentials(), client=client)

        with pytest.raises(MTConnectorRejected):
            await connector.submit_invoice(_bill(), DOCUMENT)

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_an_unreachable_platform_is_retryable(
        self, provider: EInvoicingProvider
    ) -> None:
        """A transport failure is not a rejection.

        Args:
            provider (EInvoicingProvider): The platform.
        """

        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
        connector = ConnectorFactory().build(provider, _credentials(), client=client)

        with pytest.raises(MTConnectorUnavailable):
            await connector.check_credentials()

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_failure_message_never_carries_the_key(
        self, provider: EInvoicingProvider
    ) -> None:
        """Messages reach an operator's screen and the application log.

        Args:
            provider (EInvoicingProvider): The platform.
        """
        client = _client({"": (422, {"error": "malformed"})}, [])
        connector = ConnectorFactory().build(provider, _credentials(), client=client)

        with pytest.raises(MTConnectorRejected) as raised:
            await connector.submit_invoice(_bill(), DOCUMENT)

        assert "sk_live_0123456789abcdef" not in str(raised.value)


class TestReachingAPublicBody:
    """Tests for the route only some platforms document."""

    @pytest.mark.parametrize(
        "provider",
        [
            EInvoicingProvider.B2BROUTER,
            EInvoicingProvider.INVOPOP,
            EInvoicingProvider.IOPOLE,
        ],
    )
    async def test_platforms_that_document_chorus_pro_can_send(
        self, provider: EInvoicingProvider
    ) -> None:
        """Args:
        provider (EInvoicingProvider): The platform.
        """
        client = _client({"": (200, {"id": "REF-3", "guid": "REF-3"})}, [])

        connector = ConnectorFactory().build(provider, _credentials(), client=client)
        receipt = await connector.submit_to_chorus_pro(
            _bill(RecipientKind.PUBLIC), DOCUMENT
        )

        assert receipt.kind is TransmissionKind.CHORUS_PRO
        assert receipt.succeeded() is True

    async def test_storecove_refuses_rather_than_dropping_it(self) -> None:
        """**The most important assertion about a platform we did not write.**

        Notes:
            Storecove's documentation covers French e-reporting and says
            nothing about public bodies. Accepting a département's invoice and
            sending it nowhere is indistinguishable from success until somebody
            asks where the money is, so the base class's refusal is inherited
            deliberately and asserted here so nobody "fixes" it later.
        """
        client = _client({"": (200, {"guid": "REF-3"})}, [])

        connector = ConnectorFactory().build(
            EInvoicingProvider.STORECOVE, _credentials(), client=client
        )

        with pytest.raises(MTConnectorUnsupported):
            await connector.submit_to_chorus_pro(_bill(RecipientKind.PUBLIC), DOCUMENT)

    async def test_the_refusal_tells_an_operator_what_to_do(self) -> None:
        """A refusal with no way forward is a dead end."""
        client = _client({"": (200, {"guid": "REF-3"})}, [])
        connector = ConnectorFactory().build(
            EInvoicingProvider.STORECOVE, _credentials(), client=client
        )

        with pytest.raises(MTConnectorUnsupported) as raised:
            await connector.submit_to_chorus_pro(_bill(RecipientKind.PUBLIC), DOCUMENT)

        assert "Chorus Pro" in str(raised.value)


class TestB2BRouterSubmitsThenSends:
    """Tests for the two-call sequence that protects the invoice series."""

    async def test_the_import_does_not_send(self) -> None:
        """**The flag that must stay false.**

        Notes:
            ``send_after_import=true`` would make a malformed payload and a
            transmitted invoice the same event. A rejected invoice has already
            drawn a number from a series that cannot have gaps.
        """
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"id": "INV-9"})}, seen)

        connector = ConnectorFactory().build(
            EInvoicingProvider.B2BROUTER, _credentials(), client=client
        )
        await connector.submit_invoice(_bill(), DOCUMENT)

        assert "send_after_import=false" in str(seen[0].url)

    async def test_it_sends_what_it_imported(self) -> None:
        """The identifier from the first call drives the second."""
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"id": "INV-9"})}, seen)

        connector = ConnectorFactory().build(
            EInvoicingProvider.B2BROUTER, _credentials(), client=client
        )
        await connector.submit_invoice(_bill(), DOCUMENT)

        assert len(seen) == 2
        assert str(seen[1].url).endswith("/invoices/send_invoice/INV-9")

    async def test_the_document_is_sent_as_written(self) -> None:
        """Our EN 16931 document, not a re-encoding of it.

        Notes:
            The import door is chosen over the JSON door precisely so the
            invoice's legal content stays in this repository. If this ever
            became a JSON body, that decision would have been reversed silently.
        """
        seen: List[httpx.Request] = []
        client = _client({"": (200, {"id": "INV-9"})}, seen)

        connector = ConnectorFactory().build(
            EInvoicingProvider.B2BROUTER, _credentials(), client=client
        )
        await connector.submit_invoice(_bill(), DOCUMENT)

        assert seen[0].content == DOCUMENT


class TestAMissingIdentifierDoesNotFailATransmission:
    """Tests for the tolerance that costs traceability and saves an invoice.

    Notes:
        Once a platform has answered 200 the invoice has gone. Raising over a
        response shape would record a *sent* invoice as failed and invite
        somebody to send it again — the one outcome worse than losing the
        reference.
    """

    @pytest.mark.parametrize("provider", list(EInvoicingProvider))
    async def test_a_response_without_an_identifier_still_succeeds(
        self, provider: EInvoicingProvider
    ) -> None:
        """Args:
        provider (EInvoicingProvider): The platform.
        """
        client = _client({"": (200, {"unexpected": "shape"})}, [])

        connector = ConnectorFactory().build(provider, _credentials(), client=client)
        receipt = await connector.report_payment(_bill(RecipientKind.INDIVIDUAL))

        assert receipt.succeeded() is True
        assert receipt.reference is None


class TestTheFactory:
    """Tests for the single place that maps a platform to its connector."""

    def test_every_platform_has_a_connector(self) -> None:
        """A card the gallery offers must be one that can transmit."""
        factory = ConnectorFactory()

        for provider in EInvoicingProvider:
            built = factory.build(provider, _credentials())
            assert built.PROVIDER is provider

    def test_an_unknown_platform_raises(self) -> None:
        """A miss is a programming error, not a condition to handle."""
        with pytest.raises(MTConnectorNotImplemented):
            ConnectorFactory().build("nobody", _credentials())
