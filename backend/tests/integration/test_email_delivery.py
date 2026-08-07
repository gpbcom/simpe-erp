from __future__ import annotations

# Standard library imports
from datetime import date, time
from io import BytesIO
from typing import Dict, Iterator, List
from urllib.parse import quote as urlquote

# Third-party imports
import httpx
from openpyxl import load_workbook
import pytest

# First-party imports
from models.configuration.email_config import EmailConfig
from models.enums import ContractType, InterventionStatus
from models.people.hca import Hca
from models.planning.hca_planning import HcaPlanning
from models.planning.intervention import Intervention
from service.emails.emails import EmailService

pytestmark = pytest.mark.integration

# Where Mailpit is reachable. The SMTP port is what the application writes to;
# the HTTP port is what this test reads back from — which is the only way to
# assert on *receiving* rather than merely on sending.
MAILPIT_HTTP = "http://localhost:8025"
MAILPIT_SMTP_HOST = "localhost"
MAILPIT_SMTP_PORT = 1025

ADDRESS = {
    "street": "12 rue de Rivoli",
    "postal_code": "75004",
    "city": "Paris",
    "latitude": 48.8566,
    "longitude": 2.3522,
}


@pytest.fixture(scope="session")
def mailpit() -> httpx.Client:
    """Return a client for Mailpit's REST API.

    Returns:
        httpx.Client: A client pointed at the catcher.

    Raises:
        pytest.skip.Exception: When Mailpit is not running, so the suite still
            passes on a machine without the development stack up.
    """
    client = httpx.Client(base_url=MAILPIT_HTTP, timeout=5.0)
    try:
        client.get("/api/v1/messages").raise_for_status()
    except (httpx.HTTPError, OSError):
        pytest.skip("Mailpit is not running; start the development stack first.")
    return client


@pytest.fixture(autouse=True)
def empty_inbox(mailpit: httpx.Client) -> Iterator[None]:
    """Empty the catcher before and after every test.

    Args:
        mailpit (httpx.Client): The Mailpit client.

    Yields:
        None: With an empty inbox.

    Notes:
        - **This is what makes the campaign idempotent.** Without it the second
          run asserts against the first run's messages and passes for the wrong
          reason — or fails because it found two of everything.
        - **These tests must run single-process.** The purge is global and the
          catcher is shared, so two of them on two xdist workers wipe each
          other's messages mid-assertion — and
          :meth:`test_an_empty_inbox_means_nothing_was_sent` asserts the inbox
          is empty *for the whole catcher*. ``addopts`` forces ``-n auto``, so
          the CI job passes ``-n0`` explicitly and anyone running these by hand
          must too. Three tests gain nothing from parallelism; correctness
          costs everything.
    """
    mailpit.delete("/api/v1/messages")
    yield
    mailpit.delete("/api/v1/messages")


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> EmailService:
    """Return an email service pointed at Mailpit.

    Args:
        monkeypatch (pytest.MonkeyPatch): Used to supply the credentials.

    Returns:
        EmailService: A service that really opens an SMTP connection.

    Notes:
        The credentials are nonsense, and Mailpit accepts them because the
        container runs with ``MP_SMTP_AUTH_ACCEPT_ANY``. That flag is not a
        convenience: ``EmailService._deliver`` calls ``login()``
        unconditionally, so a stub refusing authentication would fail every
        send before a message was ever built.
    """
    monkeypatch.setenv("SMTP_USERNAME", "simple-erp")
    monkeypatch.setenv("SMTP_PASSWORD", "simple-erp")
    return EmailService(
        config=EmailConfig(
            enabled=True,
            host=MAILPIT_SMTP_HOST,
            port=MAILPIT_SMTP_PORT,
            use_tls=False,
            sender="planning@simple-erp.fr",
        )
    )


def _hca() -> Hca:
    """Build an assistant to send to.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        company_id="company-1",
        id="hca-1",
        first_name="Luc",
        last_name="Martin",
        phone_number="+33698765432",
        email="luc.martin@simple-erp.fr",
        address=ADDRESS,
        contract_type=ContractType.CDI,
    )


def _planning() -> HcaPlanning:
    """Build a one-visit diary.

    Returns:
        HcaPlanning: The diary.
    """
    return HcaPlanning(
        hca_id="hca-1",
        hca_full_name="Luc Martin",
        period_start=date(2026, 8, 10),
        period_end=date(2026, 8, 16),
        interventions=[
            Intervention(
                company_id="company-1",
                id="visit-1",
                planning_run_id="run-1",
                name="Aide a la toilette",
                intervention_type_id="type-1",
                quote_line_id="line-1",
                hca_id="hca-1",
                hca_full_name="Luc Martin",
                customer_id="customer-1",
                day=date(2026, 8, 10),
                start_time=time(9, 0),
                end_time=time(10, 0),
                address=ADDRESS,
                status=InterventionStatus.PLANNED,
            )
        ],
    )


def _messages(mailpit: httpx.Client) -> List[Dict]:
    """Return every message the catcher holds.

    Args:
        mailpit (httpx.Client): The Mailpit client.

    Returns:
        List[Dict]: The messages, newest first.
    """
    return mailpit.get("/api/v1/messages").json()["messages"]


class TestPlanningEmailIsSentAndReceived:
    """Tests that an email really leaves the application and really arrives."""

    async def test_a_planning_reaches_the_assistants_inbox(
        self, service: EmailService, mailpit: httpx.Client
    ) -> None:
        """The send half and the receive half, in one test.

        Notes:
            Everything else in the suite stubs ``_deliver`` and inspects the
            ``EmailMessage`` object. That proves the message was *built*
            correctly and nothing at all about SMTP — the connection, the
            ``STARTTLS`` decision, the login, the encoding of the attachment.
            This test is the only one that exercises those.
        """
        await service.send_planning(_planning(), _hca())

        messages = _messages(mailpit)
        assert len(messages) == 1
        assert messages[0]["To"][0]["Address"] == "luc.martin@simple-erp.fr"
        assert (
            "10/08/2026" in messages[0]["Subject"] or "2026" in messages[0]["Subject"]
        )

    async def test_the_delivered_message_carries_a_readable_workbook(
        self, service: EmailService, mailpit: httpx.Client
    ) -> None:
        """The attachment survives the round trip through SMTP.

        Notes:
            An ``.xlsx`` is a zip archive. Base64 encoding, transfer and decoding
            all have to be right for it to open, and "the bytes arrived" is a
            weaker claim than "openpyxl could read it" — which is what the
            assistant's spreadsheet application will attempt.
        """
        await service.send_planning(_planning(), _hca())

        message_id = _messages(mailpit)[0]["ID"]
        detail = mailpit.get(f"/api/v1/message/{message_id}").json()
        attachments = detail["Attachments"]
        assert len(attachments) == 1
        assert attachments[0]["FileName"].endswith(".xlsx")

        payload = mailpit.get(
            f"/api/v1/message/{message_id}/part/{urlquote(attachments[0]['PartID'])}"
        ).content
        workbook = load_workbook(BytesIO(payload))
        assert workbook.active is not None

    async def test_an_empty_inbox_means_nothing_was_sent(
        self, mailpit: httpx.Client
    ) -> None:
        """The fixture really does clear the catcher.

        Notes:
            A guard on the test harness itself. If the teardown stopped working,
            every assertion above would still pass — against messages left by
            the previous run — and the campaign would silently stop testing
            anything.
        """
        assert _messages(mailpit) == []
