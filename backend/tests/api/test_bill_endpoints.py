from __future__ import annotations

# Standard library imports
from datetime import date
from decimal import Decimal
from typing import Dict, Iterator
from unittest.mock import AsyncMock, MagicMock

# Third-party imports
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_billing_service,
    get_current_user,
    get_event_publisher,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.v1.bills.settings import router as billing_settings_router
from api.v1.bills.bills import router as bills_router
from api.v1.bills.runs import router as billing_runs_router
from models.auth.user import User
from models.billing.bill import Bill
from models.billing.billing_run import BillingRun
from models.enums import (
    BillingPeriodicity,
    BillingRunStatus,
    BillStatus,
    EventRoutingKey,
    ServiceCategory,
    UserRole,
)
from models.settings.billing_settings import BillingSettings
from service.billing.billings import BillingService
from service.billing.exceptions import (
    MTBillDocumentUnavailable,
    MTBillingPeriodInFuture,
    MTBillNotFound,
    MTBillTransitionNotAllowed,
)
from service.messaging.publisher import EventPublisher
from tests.annotations import ModelInput

ADDRESS: Dict[str, ModelInput] = {
    "street": "1 rue des Lilas",
    "postal_code": "75011",
    "city": "Paris",
    "country": "France",
}
MARCH = (date(2026, 3, 1), date(2026, 3, 31))


def a_user(role: UserRole = UserRole.MANAGER) -> User:
    """Build an account.

    Args:
        role (UserRole): The role to grant.

    Returns:
        User: The account.
    """
    return User(
        company_id="company-1",
        id="user-1",
        email="manager@example.com",
        full_name="Claire Dupont",
        hashed_password="$2b$12$abcdefghijklmnopqrstuv",
        role=role,
        # An assistant account must name the record it is bound to, or the
        # model refuses to exist at all.
        hca_id="hca-1" if role is UserRole.HCA else None,
    )


def a_bill(**overrides: ModelInput) -> Bill:
    """Build a stored invoice.

    Args:
        **overrides: Fields to replace.

    Returns:
        Bill: The invoice.
    """
    payload: Dict[str, ModelInput] = {
        "id": "bill-1",
        "company_id": "company-1",
        "customer_id": "customer-1",
        "number": "FA-2026-000001",
        "sequence": 1,
        "sequence_year": 2026,
        "periodicity": BillingPeriodicity.MONTHLY,
        "period_start": MARCH[0],
        "period_end": MARCH[1],
        "issued_on": date(2026, 4, 1),
        "due_on": date(2026, 5, 1),
        "customer_full_name": "Jeanne Vincent",
        "customer_address": ADDRESS,
        "recipient": {"name": "Jeanne Vincent", "address": ADDRESS},
        "lines": [
            {
                "quote_line_id": "line-1",
                "name": "Aide à la toilette",
                "service_category": ServiceCategory.NECESSITY,
                "service_date": date(2026, 3, 9),
                "duration_minutes": 120,
                "hourly_rate_ht": Decimal("31.91"),
                "total_ht": Decimal("63.82"),
                "vat_rate": Decimal("0.055"),
                "vat_amount": Decimal("3.51"),
                "total_ttc": Decimal("67.33"),
            }
        ],
        "total_ht": Decimal("63.82"),
        "total_vat": Decimal("3.51"),
        "total_ttc": Decimal("67.33"),
        "document_key": "invoices/company-1/abc.pdf",
    }
    payload.update(overrides)
    return Bill(**payload)


def a_run(status: BillingRunStatus = BillingRunStatus.PENDING) -> BillingRun:
    """Build a stored generation run.

    Args:
        status (BillingRunStatus): The status it is in.

    Returns:
        BillingRun: The run.
    """
    return BillingRun(
        id="run-1",
        company_id="company-1",
        requested_by="user-1",
        status=status,
        reference_date=date(2026, 4, 1),
        periodicity=BillingPeriodicity.MONTHLY,
        period_start=MARCH[0],
        period_end=MARCH[1],
    )


@pytest.fixture
def service() -> MagicMock:
    """Return a billing service double.

    Returns:
        MagicMock: The double, specced so a vanished method breaks the test.
    """
    double = MagicMock(spec=BillingService)
    double.request_run = AsyncMock(return_value=a_run())
    double.get_run = AsyncMock(return_value=a_run())
    double.list_runs = AsyncMock(return_value=[a_run()])
    double.list = AsyncMock(return_value=[a_bill()])
    double.get = AsyncMock(return_value=a_bill())
    double.set_status = AsyncMock(return_value=a_bill(status=BillStatus.ACCEPTED))
    double.document = AsyncMock(return_value=(b"%PDF-1.4 stored", "FA-2026-000001.pdf"))
    double.bill_one = AsyncMock(return_value=a_bill())
    double.current_settings = AsyncMock(return_value=BillingSettings())
    double.update_settings = AsyncMock(
        return_value=BillingSettings(payment_terms_days=45, updated_by="user-1")
    )
    return double


@pytest.fixture
def publisher() -> MagicMock:
    """Return an event publisher double.

    Returns:
        MagicMock: The double, accepting every publish.
    """
    double = MagicMock(spec=EventPublisher)
    double.publish = AsyncMock(return_value=True)
    return double


@pytest.fixture
def client(service: MagicMock, publisher: MagicMock) -> Iterator[TestClient]:
    """Return a client over the three billing routers.

    Args:
        service (MagicMock): The billing service double.
        publisher (MagicMock): The event publisher double.

    Yields:
        TestClient: The client, authenticated as a manager.

    Notes:
        The service is overridden rather than reached: an API test that opened a
        real session would need Postgres and MinIO, and would hang for minutes
        when they are absent. What is under test here is the routing, the guard
        and the response shape.
    """
    app = FastAPI()
    app.include_router(billing_runs_router)
    app.include_router(bills_router)
    app.include_router(billing_settings_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_billing_service] = lambda: service
    app.dependency_overrides[get_event_publisher] = lambda: publisher
    app.dependency_overrides[get_manager_user] = lambda: a_user()
    app.dependency_overrides[get_current_user] = lambda: a_user()
    with TestClient(app) as open_client:
        yield open_client


class TestStartingARun:
    """Tests for asking a period to be billed."""

    def test_a_run_answers_202_with_something_to_poll(self, client: TestClient) -> None:
        """**202, not 200.**

        Notes:
            A monthly close renders hundreds of documents; holding the request
            open for it would time out the client. The body is the run, so the
            caller has an identifier to poll.
        """
        answer = client.post(
            "/api/v1/bills/runs", json={"reference_date": "2026-03-15"}
        )

        assert answer.status_code == 202
        assert answer.json()["id"] == "run-1"
        assert answer.json()["status"] == "pending"

    def test_the_run_is_announced_to_a_worker(
        self, client: TestClient, publisher: MagicMock
    ) -> None:
        """Recorded first, then queued.

        Args:
            publisher (MagicMock): The event publisher double.
        """
        client.post("/api/v1/bills/runs", json={"reference_date": "2026-03-15"})

        publisher.publish.assert_awaited_once()
        assert publisher.publish.await_args.args[1] == "company-1"

    def test_an_unfinished_period_is_refused(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """Care that has not happened cannot be invoiced.

        Args:
            service (MagicMock): The billing service double.
        """
        service.request_run = AsyncMock(
            side_effect=MTBillingPeriodInFuture("not finished")
        )

        answer = client.post(
            "/api/v1/bills/runs", json={"reference_date": "2026-03-15"}
        )

        assert answer.status_code == 422

    def test_a_run_without_a_day_is_refused(self, client: TestClient) -> None:
        """There is no default period; billing the wrong month is expensive."""
        assert client.post("/api/v1/bills/runs", json={}).status_code == 422

    def test_a_missing_run_answers_404(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """Polling an identifier for nothing is told so.

        Args:
            service (MagicMock): The billing service double.
        """
        service.get_run = AsyncMock(side_effect=MTBillNotFound("no such run"))

        assert client.get("/api/v1/bills/runs/nope").status_code == 404


class TestTheRunPathIsNotSwallowed:
    """Tests for the routing hazard the two path shapes create."""

    def test_the_run_list_is_not_matched_as_a_bill(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """**``/bills/runs`` and ``/bills/{bill_id}`` match the same shape.**

        Args:
            service (MagicMock): The billing service double.

        Notes:
            Registered in the wrong order, asking for the run list would look up
            a bill numbered "runs" and answer 404. The routers are mounted runs
            first, and this is what proves it stays that way.
        """
        answer = client.get("/api/v1/bills/runs")

        assert answer.status_code == 200
        service.list_runs.assert_awaited_once()
        service.get.assert_not_awaited()

    def test_billing_one_customer_is_not_matched_as_a_bill(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The static ``customers`` segment keeps the two apart.

        Args:
            service (MagicMock): The billing service double.
        """
        answer = client.post(
            "/api/v1/bills/customers/customer-1?reference_date=2026-03-15"
        )

        assert answer.status_code == 200
        service.bill_one.assert_awaited_once()


class TestReadingBills:
    """Tests for the list and the detail."""

    def test_the_list_is_scoped_to_the_caller_s_agency(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The agency comes from the credential, never from the query.

        Args:
            service (MagicMock): The billing service double.
        """
        client.get("/api/v1/bills")

        assert service.list.await_args.args[0] == "company-1"

    def test_a_cleared_select_or_date_is_not_a_rejection(
        self, client: TestClient
    ) -> None:
        """**A select or a date picker reset to blank submits ``""``.**

        Notes:
            Declared as the enum or the date, FastAPI would refuse ``?status=``
            before the filter's own validator ran, and the screen would answer
            422 every time somebody cleared a box. Declared as strings, the
            filter's ``""`` means "not applied".

            A cleared **flag** is a different case: the shared
            :meth:`~models.base.entity_filter.EntityFilter.validate_flag`
            accepts only a boolean or nothing, so a filter bar drops the
            parameter rather than emptying it — the behaviour every other list
            screen already has.
        """
        answer = client.get("/api/v1/bills?status=&period_start=&period_end=")

        assert answer.status_code == 200

    def test_a_flag_is_dropped_rather_than_emptied(self, client: TestClient) -> None:
        """The house-wide contract for a three-state flag.

        Notes:
            ``?is_sent=`` is refused exactly as ``?auto_renew=`` is on the quote
            list. The three states are true, false and absent, and an empty
            string is none of them.
        """
        assert client.get("/api/v1/bills?is_sent=true").status_code == 200
        assert client.get("/api/v1/bills?is_sent=").status_code == 422

    def test_an_unknown_status_is_refused(self, client: TestClient) -> None:
        """A filter the server cannot narrow by is the caller's to correct."""
        assert client.get("/api/v1/bills?status=archived").status_code == 422

    def test_a_bill_comes_back_with_its_charges(self, client: TestClient) -> None:
        """The detail drawer reads the visits from here."""
        body = client.get("/api/v1/bills/bill-1").json()

        assert body["number"] == "FA-2026-000001"
        assert body["lines"][0]["name"] == "Aide à la toilette"
        assert body["total_ttc"] == "67.33"

    def test_a_missing_bill_answers_404(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """Absence is a 404, not a 500.

        Args:
            service (MagicMock): The billing service double.
        """
        service.get = AsyncMock(side_effect=MTBillNotFound("no such bill"))

        assert client.get("/api/v1/bills/nope").status_code == 404


class TestTheLifecycleEndpoint:
    """Tests for moving an invoice, which is what sends it."""

    def test_approving_an_invoice_announces_it(
        self, client: TestClient, publisher: MagicMock
    ) -> None:
        """**Published after the record says a human approved it.**

        Args:
            publisher (MagicMock): The event publisher double.

        Notes:
            Never before. A generation run leaves every invoice waiting
            precisely so nothing reaches a customer un-approved.
        """
        answer = client.patch(
            "/api/v1/bills/bill-1/status", json={"status": "accepted"}
        )

        assert answer.status_code == 200
        publisher.publish.assert_awaited_once()
        assert publisher.publish.await_args.args[2]["bill_id"] == "bill-1"

    def test_marking_it_paid_declares_it_without_re_sending_it(
        self, client: TestClient, service: MagicMock, publisher: MagicMock
    ) -> None:
        """**Two obligations, and only one of them reaches the customer.**

        Args:
            service (MagicMock): The billing service double.
            publisher (MagicMock): The event publisher double.

        Notes:
            Marking an invoice paid must not re-send it — the customer already
            has it — but collection *is* a reportable event: VAT on services
            falls due when the money arrives, so the settlement is declared to
            the tax authority. The two travel on different routing keys, and
            asserting the key rather than merely "something was published" is
            what keeps a settled invoice out of the customer's inbox.
        """
        service.set_status = AsyncMock(return_value=a_bill(status=BillStatus.PAID))

        client.patch("/api/v1/bills/bill-1/status", json={"status": "paid"})

        publisher.publish.assert_awaited_once()
        assert publisher.publish.await_args.args[0] is EventRoutingKey.BILL_PAID
        assert publisher.publish.await_args.args[2]["bill_id"] == "bill-1"

    def test_a_move_that_is_neither_approval_nor_payment_announces_nothing(
        self, client: TestClient, service: MagicMock, publisher: MagicMock
    ) -> None:
        """The other transitions are bookkeeping and reach nobody.

        Args:
            service (MagicMock): The billing service double.
            publisher (MagicMock): The event publisher double.
        """
        service.set_status = AsyncMock(
            return_value=a_bill(status=BillStatus.WAITING_PAYMENT)
        )

        client.patch("/api/v1/bills/bill-1/status", json={"status": "waiting-payment"})

        publisher.publish.assert_not_awaited()

    def test_a_skip_answers_409(self, client: TestClient, service: MagicMock) -> None:
        """Well formed, wrong state — a conflict, not a malformed payload.

        Args:
            service (MagicMock): The billing service double.
        """
        service.set_status = AsyncMock(
            side_effect=MTBillTransitionNotAllowed("skips a step")
        )

        answer = client.patch("/api/v1/bills/bill-1/status", json={"status": "paid"})

        assert answer.status_code == 409

    def test_an_unknown_status_is_refused(self, client: TestClient) -> None:
        """A status change whose content is nonsense is an empty instruction."""
        answer = client.patch(
            "/api/v1/bills/bill-1/status", json={"status": "archived"}
        )

        assert answer.status_code == 422


class TestDownloadingTheDocument:
    """Tests for streaming an invoice back."""

    def test_the_pdf_is_served_as_an_attachment(self, client: TestClient) -> None:
        """**Streamed through the bearer guard, never from the bucket.**

        Notes:
            The objects live under a private prefix precisely so this endpoint
            is the only way to them.
        """
        answer = client.get("/api/v1/bills/bill-1/document")

        assert answer.status_code == 200
        assert answer.headers["content-type"] == "application/pdf"
        assert (
            answer.headers["content-disposition"]
            == 'attachment; filename="FA-2026-000001.pdf"'
        )
        assert answer.content.startswith(b"%PDF-")

    def test_the_filename_comes_from_the_service(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """Never from anything the caller sends.

        Args:
            service (MagicMock): The billing service double.
        """
        client.get("/api/v1/bills/bill-1/document")

        service.document.assert_awaited_once_with("bill-1")

    def test_an_unreadable_document_answers_503(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """The invoice exists. The store is what did not answer.

        Args:
            service (MagicMock): The billing service double.
        """
        service.document = AsyncMock(
            side_effect=MTBillDocumentUnavailable("store down")
        )

        assert client.get("/api/v1/bills/bill-1/document").status_code == 503

    def test_the_schema_declares_the_content_type(self) -> None:
        """A body of bytes has no model to infer it from.

        Notes:
            Without the explicit ``responses`` block the generated schema would
            claim the endpoint returns JSON, and the drift job would carry that
            claim into the hand-written client.
        """
        app = FastAPI()
        app.include_router(bills_router)
        operation = app.openapi()["paths"]["/api/v1/bills/{bill_id}/document"]

        assert "application/pdf" in operation["get"]["responses"]["200"]["content"]


class TestTheSettingsEndpoints:
    """Tests for the rules a manager owns."""

    def test_the_rules_are_readable(self, client: TestClient) -> None:
        """Seeded on first read, so a screen never has to handle a 404."""
        body = client.get("/api/v1/billing/settings").json()

        assert body["periodicity"] == "monthly"
        assert body["payment_terms_days"] == 30

    def test_the_whole_rule_set_is_sent_on_save(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """**Never a partial body.**

        Args:
            service (MagicMock): The billing service double.

        Notes:
            Every field carries a default matching the stored model's, so a
            payload omitting one would silently reset a value printed on every
            invoice the agency sends.
        """
        answer = client.put("/api/v1/billing/settings", json={"payment_terms_days": 45})

        assert answer.status_code == 200
        request = service.update_settings.await_args.args[0]
        assert request.payment_terms_days == 45
        assert request.periodicity is BillingPeriodicity.MONTHLY

    def test_a_change_is_attributed(
        self, client: TestClient, service: MagicMock
    ) -> None:
        """A change to what customers are told has a name attached.

        Args:
            service (MagicMock): The billing service double.
        """
        client.put("/api/v1/billing/settings", json={"payment_terms_days": 45})

        assert service.update_settings.await_args.args[1] == "user-1"

    def test_terms_beyond_the_statutory_ceiling_are_refused(
        self, client: TestClient
    ) -> None:
        """The outer of two gates, naming the field the caller got wrong."""
        answer = client.put("/api/v1/billing/settings", json={"payment_terms_days": 90})

        assert answer.status_code == 422


class TestTheGuards:
    """Tests that every route is behind the manager gate."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            pytest.param("get", "/api/v1/bills", id="the list"),
            pytest.param("get", "/api/v1/bills/bill-1", id="one invoice"),
            pytest.param("get", "/api/v1/bills/bill-1/document", id="the document"),
            pytest.param("get", "/api/v1/bills/runs", id="the run list"),
            pytest.param("get", "/api/v1/bills/runs/run-1", id="one run"),
            pytest.param("get", "/api/v1/billing/settings", id="the rules"),
        ],
    )
    def test_an_assistant_is_refused(
        self, service: MagicMock, publisher: MagicMock, method: str, path: str
    ) -> None:
        """**Money is not an assistant's to read.**

        Args:
            service (MagicMock): The billing service double.
            publisher (MagicMock): The event publisher double.
            method (str): The HTTP method.
            path (str): The path being guarded.

        Notes:
            The real guard runs here: only the *account* is planted, on the
            request state where the authentication middleware would put it, so
            a route that lost its ``Depends(get_manager_user)`` fails this test
            rather than passing against a mocked gate.
        """
        app = FastAPI()
        app.include_router(billing_runs_router)
        app.include_router(bills_router)
        app.include_router(billing_settings_router)
        ExceptionHandlers().register(app)
        app.dependency_overrides[get_billing_service] = lambda: service
        app.dependency_overrides[get_event_publisher] = lambda: publisher

        @app.middleware("http")
        async def _authenticate(
            request: Request, call_next: RequestResponseEndpoint
        ) -> Response:
            """Plant an assistant where the real middleware would.

            Args:
                request (Request): The incoming request.
                call_next (RequestResponseEndpoint): The rest of the stack.

            Returns:
                Response: The response.
            """
            request.state.user = a_user(UserRole.HCA)
            return await call_next(request)

        with TestClient(app) as guarded:
            assert getattr(guarded, method)(path).status_code == 403
