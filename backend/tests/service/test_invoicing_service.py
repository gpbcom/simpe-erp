from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
import pathlib
from typing import Dict, List, Optional

# Third-party imports
import httpx
import pytest

# First-party imports
from integrations.base import InvoicingConnector
from integrations.factory import ConnectorFactory
from models.billing.bill import Bill
from models.configuration.app_config import AppConfig
from models.configuration.integration_config import IntegrationConfig
from models.enums import (
    BillingPeriodicity,
    BillStatus,
    EInvoicingProvider,
    RecipientKind,
    ServiceCategory,
    TransmissionKind,
    TransmissionStatus,
)
from models.integrations.einvoicing_integration import EInvoicingIntegration
from models.integrations.integration_credentials import IntegrationCredentials
from service.integrations.exceptions import (
    MTIntegrationCredentialsRefused,
    MTIntegrationNotConfigured,
    MTNoActivePlatform,
)
from service.integrations.invoicing import InvoicingService
from service.security.credential_cipher import CredentialCipher

#: The catalogue as the shipped configuration declares it. Read from the file
#: rather than hand-written, because the gallery this service feeds is only as
#: complete as ``conf/app.yaml`` is.
CONFIGURED = AppConfig.load(
    pathlib.Path(__file__).resolve().parents[2] / "conf" / "app.yaml"
).integrations
COMPANY = "company-1"
ACTOR = "nathalie@simple-erp.fr"
DOCUMENT = b"<CrossIndustryInvoice/>"


class _Repository:
    """An in-memory stand-in for the integrations repository.

    Notes:
        A fake rather than the real repository on SQLite, because what these
        tests are about is the *service's* decisions — proving credentials
        before storing them, refusing to transmit with nothing connected. The
        repository's own invariants are tested against a real database in
        ``tests/storage``.
    """

    def __init__(self) -> None:
        """Start with nothing configured."""
        self.rows: Dict[EInvoicingProvider, EInvoicingIntegration] = {}
        self.checks: List[Optional[str]] = []

    async def list_for_company(self, company_id: str) -> List[EInvoicingIntegration]:
        """Return every stored integration.

        Args:
            company_id (str): Ignored; the fake holds one agency.

        Returns:
            List[EInvoicingIntegration]: What is stored.
        """
        return list(self.rows.values())

    async def get_enabled(self, company_id: str) -> Optional[EInvoicingIntegration]:
        """Return the enabled integration, if any.

        Args:
            company_id (str): Ignored.

        Returns:
            Optional[EInvoicingIntegration]: The enabled one, or ``None``.
        """
        for row in self.rows.values():
            if row.enabled:
                return row
        return None

    async def get_for_provider(
        self, company_id: str, provider: EInvoicingProvider
    ) -> Optional[EInvoicingIntegration]:
        """Return one platform's integration.

        Args:
            company_id (str): Ignored.
            provider (EInvoicingProvider): The platform.

        Returns:
            Optional[EInvoicingIntegration]: The integration, or ``None``.
        """
        return self.rows.get(provider)

    async def enable(
        self,
        company_id: str,
        provider: EInvoicingProvider,
        ciphertext: str,
        hint: str,
        actor: str,
    ) -> EInvoicingIntegration:
        """Store credentials and make the platform the only active one.

        Args:
            company_id (str): The agency.
            provider (EInvoicingProvider): The platform.
            ciphertext (str): The sealed credentials.
            hint (str): The masked tail.
            actor (str): Who did it.

        Returns:
            EInvoicingIntegration: The stored integration.
        """
        for key, row in list(self.rows.items()):
            if key is not provider:
                self.rows[key] = row.model_copy(update={"enabled": False})
        stored = EInvoicingIntegration(
            id=f"integration-{provider.value}",
            company_id=company_id,
            provider=provider,
            enabled=True,
            credential_ciphertext=ciphertext,
            credential_hint=hint,
            updated_by=actor,
        )
        self.rows[provider] = stored
        return stored

    async def disable(
        self, company_id: str, provider: EInvoicingProvider, actor: str
    ) -> Optional[EInvoicingIntegration]:
        """Switch a platform off.

        Args:
            company_id (str): Ignored.
            provider (EInvoicingProvider): The platform.
            actor (str): Who did it.

        Returns:
            Optional[EInvoicingIntegration]: The disabled integration.
        """
        row = self.rows.get(provider)
        if row is None:
            return None
        self.rows[provider] = row.model_copy(update={"enabled": False})
        return self.rows[provider]

    async def record_check(
        self, company_id: str, provider: EInvoicingProvider, error: Optional[str]
    ) -> Optional[EInvoicingIntegration]:
        """Record the outcome of a credentials check.

        Args:
            company_id (str): Ignored.
            provider (EInvoicingProvider): The platform.
            error (Optional[str]): The failure, or ``None``.

        Returns:
            Optional[EInvoicingIntegration]: The updated integration.
        """
        self.checks.append(error)
        row = self.rows.get(provider)
        if row is None:
            return None
        self.rows[provider] = row.model_copy(update={"last_check_error": error})
        return self.rows[provider]


def _bill(kind: RecipientKind = RecipientKind.INDIVIDUAL) -> Bill:
    """Build a settled invoice addressed to a recipient of a given kind.

    Args:
        kind (RecipientKind): Who owes the money.

    Returns:
        Bill: The invoice.
    """
    address = {
        "street": "12 rue de la Paix",
        "postal_code": "75002",
        "city": "Paris",
        "country": "France",
        "latitude": 48.86,
        "longitude": 2.33,
    }
    recipient: Dict[str, object] = {"kind": kind, "name": "Payeur", "address": address}
    if kind is not RecipientKind.INDIVIDUAL:
        recipient["siren"] = "552100554"
    if kind is RecipientKind.PUBLIC:
        recipient["service_code"] = "APA-01"
    return Bill(
        id="bill-1",
        company_id=COMPANY,
        number="FA-2026-0001",
        sequence=1,
        sequence_year=2026,
        periodicity=BillingPeriodicity.MONTHLY,
        customer_id="customer-1",
        customer_full_name="Marie Durand",
        customer_address=address,
        recipient=recipient,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        issued_on=date(2026, 8, 1),
        due_on=date(2026, 8, 31),
        status=BillStatus.PAID,
        document_key="invoices/company-1/FA-2026-0001.pdf",
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


def _client(status: int, body: object, seen: List[httpx.Request]) -> httpx.AsyncClient:
    """Build a client answering everything the same way.

    Args:
        status (int): The status to answer.
        body (object): The JSON body to answer.
        seen (List[httpx.Request]): Collects every request made.

    Returns:
        httpx.AsyncClient: The client.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


@pytest.fixture
def cipher(monkeypatch: pytest.MonkeyPatch) -> CredentialCipher:
    """Build a cipher on a test secret.

    Args:
        monkeypatch (pytest.MonkeyPatch): The patcher.

    Returns:
        CredentialCipher: The cipher.
    """
    config = IntegrationConfig()
    monkeypatch.setenv(config.credential_key_env, "a-long-enough-test-secret")
    return CredentialCipher(config)


class _Factory(ConnectorFactory):
    """A factory that hands every connector the suite's stubbed client.

    Attributes:
        client (Optional[httpx.AsyncClient]): The client to inject.

    Notes:
        A subclass rather than a rebound attribute so the override is visible
        where it is read. The real factory decides *which* connector; only the
        transport is stubbed, so the connectors under test are the shipped ones.
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """Initialize the factory.

        Args:
            client (Optional[httpx.AsyncClient]): The client to inject.
        """
        super().__init__()
        self.client = client

    def build(
        self,
        provider: EInvoicingProvider,
        credentials: IntegrationCredentials,
        timeout_seconds: float = 30.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> InvoicingConnector:
        """Return a connector wired to the suite's transport.

        Args:
            provider (EInvoicingProvider): The platform.
            credentials (IntegrationCredentials): What it authenticates on.
            timeout_seconds (float): How long to wait on it.
            client (Optional[httpx.AsyncClient]): Ignored; the injected one wins.

        Returns:
            InvoicingConnector: The connector.
        """
        return super().build(provider, credentials, timeout_seconds, self.client)


def _service(
    repository: _Repository,
    cipher: CredentialCipher,
    client: Optional[httpx.AsyncClient] = None,
) -> InvoicingService:
    """Build the integration service over a fake repository.

    Args:
        repository (_Repository): The stand-in store.
        cipher (CredentialCipher): The cipher.
        client (Optional[httpx.AsyncClient]): The platform client to use.

    Returns:
        InvoicingService: The service.
    """
    return InvoicingService(
        integrations=repository,
        cipher=cipher,
        config=CONFIGURED,
        connectors=_Factory(client),
    )


class TestSeeingWhatIsAvailable:
    """Tests for what the gallery is drawn from."""

    async def test_every_platform_gets_a_card(self, cipher: CredentialCipher) -> None:
        """**A gallery that showed only what was connected would start empty.**

        Args:
            cipher (CredentialCipher): The cipher.
        """
        service = _service(_Repository(), cipher)

        cards = await service.list_cards(COMPANY)

        assert len(cards) == len(EInvoicingProvider)
        assert all(card.configured is False for card in cards)

    async def test_no_card_carries_a_secret(self, cipher: CredentialCipher) -> None:
        """**The assertion the whole storage design exists for.**

        Args:
            cipher (CredentialCipher): The cipher.
        """
        repository = _Repository()
        seen: List[httpx.Request] = []
        service = _service(repository, cipher, _client(200, {"ok": True}, seen))
        await service.enable(
            COMPANY,
            EInvoicingProvider.STORECOVE,
            IntegrationCredentials(
                api_key="sk_live_0123456789abcdef", legal_entity_id="entity-1"
            ),
            ACTOR,
        )

        cards = await service.list_cards(COMPANY)
        payload = [card.model_dump_json() for card in cards]

        assert not any("sk_live_0123456789abcdef" in entry for entry in payload)
        assert any("…cdef" in entry for entry in payload)

    async def test_an_agency_with_nothing_is_reported_as_such(
        self, cipher: CredentialCipher
    ) -> None:
        """What the warning banner is drawn from.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        service = _service(_Repository(), cipher)

        assert await service.has_active_platform(COMPANY) is False


class TestConnectingAPlatform:
    """Tests for the order in which a key is proven and stored."""

    async def test_a_working_key_is_stored_and_enabled(
        self, cipher: CredentialCipher
    ) -> None:
        """Args:
        cipher (CredentialCipher): The cipher.
        """
        repository = _Repository()
        service = _service(repository, cipher, _client(200, {"ok": True}, []))

        stored = await service.enable(
            COMPANY,
            EInvoicingProvider.IOPOLE,
            IntegrationCredentials(api_key="sk_live_0123456789abcdef"),
            ACTOR,
        )

        assert stored.enabled is True
        assert await service.has_active_platform(COMPANY) is True

    async def test_the_stored_credentials_can_be_opened_again(
        self, cipher: CredentialCipher
    ) -> None:
        """A connector must get the key back, or none of this works.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        repository = _Repository()
        service = _service(repository, cipher, _client(200, {"ok": True}, []))
        credentials = IntegrationCredentials(api_key="sk_live_0123456789abcdef")

        stored = await service.enable(
            COMPANY, EInvoicingProvider.IOPOLE, credentials, ACTOR
        )

        assert cipher.open(stored.credential_ciphertext) == credentials

    async def test_a_refused_key_is_not_stored(
        self, cipher: CredentialCipher
    ) -> None:
        """**Proven first, stored second.**

        Args:
            cipher (CredentialCipher): The cipher.

        Notes:
            Storing an unproven key would enable a platform that cannot be
            reached, and clear a warning banner that was telling the truth.
        """
        repository = _Repository()
        service = _service(repository, cipher, _client(401, {"error": "bad"}, []))

        with pytest.raises(MTIntegrationCredentialsRefused):
            await service.enable(
                COMPANY,
                EInvoicingProvider.IOPOLE,
                IntegrationCredentials(api_key="sk_live_0123456789abcdef"),
                ACTOR,
            )

        assert repository.rows == {}
        assert await service.has_active_platform(COMPANY) is False

    async def test_the_refusal_says_what_to_do(
        self, cipher: CredentialCipher
    ) -> None:
        """The connector's message is the actionable half.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        service = _service(_Repository(), cipher, _client(401, {"error": "bad"}, []))

        with pytest.raises(MTIntegrationCredentialsRefused) as raised:
            await service.enable(
                COMPANY,
                EInvoicingProvider.IOPOLE,
                IntegrationCredentials(api_key="sk_live_0123456789abcdef"),
                ACTOR,
            )

        assert "API key" in str(raised.value)

    async def test_disabling_something_never_connected_is_refused(
        self, cipher: CredentialCipher
    ) -> None:
        """Args:
        cipher (CredentialCipher): The cipher.
        """
        service = _service(_Repository(), cipher)

        with pytest.raises(MTIntegrationNotConfigured):
            await service.disable(COMPANY, EInvoicingProvider.IOPOLE, ACTOR)


class TestTransmittingASettledInvoice:
    """Tests for requirement 6, and for the routing it actually needs.

    Notes:
        "Send the paid bill to the platform" is right for a business and wrong
        for a household — most of this agency's revenue is B2C, where the
        obligation is to *declare* the collection rather than deliver a
        document to anybody.
    """

    @pytest.mark.parametrize(
        "kind,expected",
        [
            (RecipientKind.INDIVIDUAL, TransmissionKind.PAYMENT_REPORT),
            (RecipientKind.BUSINESS, TransmissionKind.INVOICE),
            (RecipientKind.PUBLIC, TransmissionKind.CHORUS_PRO),
        ],
    )
    async def test_it_transmits_what_the_recipient_calls_for(
        self,
        cipher: CredentialCipher,
        kind: RecipientKind,
        expected: TransmissionKind,
    ) -> None:
        """Args:
        cipher (CredentialCipher): The cipher.
        kind (RecipientKind): Who owes the money.
        expected (TransmissionKind): What must be transmitted.
        """
        repository = _Repository()
        integrations = _service(
            repository, cipher, _client(200, {"id": "REF-1", "guid": "REF-1"}, [])
        )
        await integrations.enable(
            COMPANY,
            EInvoicingProvider.B2BROUTER,
            IntegrationCredentials(
                api_key="sk_live_0123456789abcdef", account_id="acct-1"
            ),
            ACTOR,
        )

        receipt = await integrations.transmit(
            _bill(kind), DOCUMENT
        )

        assert receipt.kind is expected
        assert receipt.succeeded() is True

    async def test_nothing_connected_is_refused_loudly(
        self, cipher: CredentialCipher
    ) -> None:
        """**The one failure that raises rather than being recorded.**

        Args:
            cipher (CredentialCipher): The cipher.

        Notes:
            It is not an attempt that went wrong but one that could not be
            made, and the answer is a screen telling somebody to connect a
            platform rather than a row to retry.
        """
        service = _service(_Repository(), cipher)

        with pytest.raises(MTNoActivePlatform):
            await service.transmit(_bill(), DOCUMENT)

    async def test_a_platform_failure_is_recorded_rather_than_raised(
        self, cipher: CredentialCipher
    ) -> None:
        """**A failed transmission must never look like a failed payment.**

        Args:
            cipher (CredentialCipher): The cipher.

        Notes:
            The money is settled whatever the platform said. Raising here would
            turn a working payment into a 500 on the webhook that carries it,
            which would then be redelivered.
        """
        repository = _Repository()
        integrations = _service(
            repository, cipher, _client(200, {"id": "REF-1"}, [])
        )
        await integrations.enable(
            COMPANY,
            EInvoicingProvider.B2BROUTER,
            IntegrationCredentials(
                api_key="sk_live_0123456789abcdef", account_id="acct-1"
            ),
            ACTOR,
        )
        broken = _service(repository, cipher, _client(503, {"error": "down"}, []))

        receipt = await broken.transmit(_bill(), DOCUMENT)

        assert receipt.status is TransmissionStatus.FAILED
        assert receipt.error

    async def test_a_platform_that_cannot_reach_a_public_body_says_so(
        self, cipher: CredentialCipher
    ) -> None:
        """Storecove refuses a département rather than dropping the invoice.

        Args:
            cipher (CredentialCipher): The cipher.
        """
        repository = _Repository()
        integrations = _service(
            repository, cipher, _client(200, {"guid": "REF-1"}, [])
        )
        await integrations.enable(
            COMPANY,
            EInvoicingProvider.STORECOVE,
            IntegrationCredentials(
                api_key="sk_live_0123456789abcdef", legal_entity_id="entity-1"
            ),
            ACTOR,
        )

        receipt = await integrations.transmit(
            _bill(RecipientKind.PUBLIC), DOCUMENT
        )

        assert receipt.status is TransmissionStatus.FAILED
        assert "Chorus Pro" in receipt.error
