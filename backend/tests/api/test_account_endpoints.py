from __future__ import annotations

# Standard library imports
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import AsyncIterator, Optional
from unittest.mock import AsyncMock

# Third-party imports
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# First-party imports
from api.dependencies import (
    get_auth_service,
    get_company_service,
    get_current_user,
    get_hca_application_service,
    get_manager_user,
)
from api.exception_handlers import ExceptionHandlers
from api.middleware import auth_middleware
from api.middleware.auth_middleware import AuthMiddleware
from api.v1.auth.accounts import router as accounts_router
from api.v1.companies.companies import router as companies_router
from api.v1.hcas.applications import router as applications_router
from models.auth.user import User
from models.companies.company import Company
from models.companies.company_choice import CompanyChoice
from models.enums import (
    AccountOrigin,
    ContractType,
    HcaApplicationStatus,
    UserRole,
)
from models.people.hca_application import HcaApplication
from service.auth.exceptions import MTAuthSamePassword
from service.companies.exceptions import MTCompanyNotAcceptingApplications
from service.hcas.exceptions import MTApplicationForbidden

HASH = "$2b$12$" + "a" * 53

APPLICATION_PAYLOAD = {
    "company_id": "company-1",
    "first_name": "Ana",
    "last_name": "Lopez",
    "phone_number": "+33611223344",
    "email": "ana.lopez@example.com",
    "password": "ChosenPassphrase!",
    "address": {
        "street": "9 rue Oberkampf",
        "postal_code": "75011",
        "city": "Paris",
    },
}


def _user(
    role: UserRole = UserRole.MANAGER,
    must_change: bool = False,
    company_id: Optional[str] = "company-1",
) -> User:
    """Build an account for a role.

    Args:
        role (UserRole): The role to grant.
        must_change (bool): Whether a temporary password is still in force.
        company_id (Optional[str]): The company it belongs to.

    Returns:
        User: The account.
    """
    return User(
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name="Test Account",
        hashed_password=HASH,
        role=role,
        hca_id="hca-1" if role is UserRole.HCA else None,
        company_id=company_id,
        account_origin=(
            AccountOrigin.CREATED_BY_STAFF
            if must_change
            else AccountOrigin.SELF_REGISTERED
        ),
        must_change_password=must_change,
    )


def _application() -> HcaApplication:
    """Build a pending application.

    Returns:
        HcaApplication: The application.
    """
    return HcaApplication(
        id="application-1",
        company_id="company-1",
        first_name="Ana",
        last_name="Lopez",
        phone_number="+33611223344",
        email="ana.lopez@example.com",
        address={
            "street": "9 rue Oberkampf",
            "postal_code": "75011",
            "city": "Paris",
        },
        hashed_password=HASH,
    )


def _client(
    applications: AsyncMock,
    companies: AsyncMock,
    auth: AsyncMock,
    caller: User = None,
) -> TestClient:
    """Build a client for the account routers alone.

    Args:
        applications (AsyncMock): The stubbed application service.
        companies (AsyncMock): The stubbed company service.
        auth (AsyncMock): The stubbed authentication service.
        caller (User): The account the request is authenticated as.

    Returns:
        TestClient: A client over an app mounting only the routers under test.
    """
    caller = caller if caller else _user()
    app = FastAPI()
    app.include_router(accounts_router)
    app.include_router(companies_router)
    app.include_router(applications_router)
    ExceptionHandlers().register(app)
    app.dependency_overrides[get_hca_application_service] = lambda: applications
    app.dependency_overrides[get_company_service] = lambda: companies
    app.dependency_overrides[get_auth_service] = lambda: auth
    app.dependency_overrides[get_manager_user] = lambda: caller
    app.dependency_overrides[get_current_user] = lambda: caller
    return TestClient(app)


@pytest.fixture
def applications() -> AsyncMock:
    """Return a stubbed application service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.submit.return_value = _application()
    stub.get.return_value = _application()
    stub.list_pending.return_value = [_application()]
    stub.approve.return_value = _application().model_copy(
        update={
            "status": HcaApplicationStatus.APPROVED,
            "decided_by": "user-manager",
            "hca_id": "hca-new",
        }
    )
    stub.reject.return_value = _application().model_copy(
        update={
            "status": HcaApplicationStatus.REJECTED,
            "decided_by": "user-manager",
        }
    )
    return stub


@pytest.fixture
def companies() -> AsyncMock:
    """Return a stubbed company service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.choices.return_value = [CompanyChoice(id="company-1", name="Aide et Soins")]
    stub.create.return_value = Company(id="company-1", name="Aide et Soins")
    stub.get.return_value = Company(id="company-1", name="Aide et Soins")
    stub.list.return_value = [Company(id="company-1", name="Aide et Soins")]
    return stub


@pytest.fixture
def auth() -> AsyncMock:
    """Return a stubbed authentication service.

    Returns:
        AsyncMock: The service double.
    """
    stub = AsyncMock()
    stub.create_staff_account.return_value = (
        User(
            company_id="company-1",
            id="user-new",
            email="new@example.com",
            full_name="New Starter",
            hashed_password=HASH,
            role=UserRole.HCA,
            hca_id="hca-1",
            account_origin=AccountOrigin.CREATED_BY_STAFF,
            must_change_password=True,
        ),
        "GeneratedPass123",
    )
    stub.change_password.return_value = _user().model_copy(
        update={"password_changed_at": datetime.now(UTC)}
    )
    return stub


class TestPublicApplicationEndpoints:
    """Tests for the routes an applicant reaches without a credential."""

    def test_the_company_list_needs_no_credential(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """An applicant cannot choose a company without seeing the list.

        Notes:
            The route has no guard at all, which is deliberate and stated: the
            person calling it has no account yet, by definition.
        """
        response = _client(applications, companies, auth).get(
            "/api/v1/companies/choices"
        )

        assert response.status_code == 200
        assert response.json() == [{"id": "company-1", "name": "Aide et Soins"}]

    def test_the_company_list_carries_nothing_but_names(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The response shape is what stops an agency directory leaking.

        Notes:
            An unauthenticated endpoint returning whole companies would publish
            every agency's registered office and contact address to anybody who
            asks.
        """
        response = _client(applications, companies, auth).get(
            "/api/v1/companies/choices"
        )

        assert set(response.json()[0]) == {"id", "name"}

    def test_an_application_can_be_submitted_without_a_credential(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """This is how somebody with no account asks for one."""
        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications", json=APPLICATION_PAYLOAD
        )

        assert response.status_code == 201
        assert response.json()["status"] == HcaApplicationStatus.PENDING.value

    def test_the_submitted_password_is_not_echoed_back(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """A response carrying the password back would put it in every proxy log."""
        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications", json=APPLICATION_PAYLOAD
        )

        assert "ChosenPassphrase!" not in response.text

    def test_an_application_cannot_ask_for_a_role(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """An unauthenticated caller cannot ask to be an administrator.

        Notes:
            There is no ``role`` field on the request model, so the value has
            nowhere to go. The service is what would use it, and it is never
            called with one.
        """
        _client(applications, companies, auth).post(
            "/api/v1/hca-applications",
            json={**APPLICATION_PAYLOAD, "role": "admin"},
        )

        assert "role" not in applications.submit.await_args.kwargs

    def test_a_weak_password_is_refused(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The policy applies on the public path too."""
        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications",
            json={**APPLICATION_PAYLOAD, "password": "short"},
        )

        assert response.status_code == 422
        applications.submit.assert_not_awaited()

    def test_applying_with_no_company_is_refused(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """Choosing the company is the applicant's decision to make."""
        payload = {**APPLICATION_PAYLOAD}
        payload.pop("company_id")

        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications", json=payload
        )

        assert response.status_code == 422

    def test_a_closed_company_answers_409(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """ "Not hiring" is a conflict, not a not-found."""
        applications.submit.side_effect = MTCompanyNotAcceptingApplications("closed")

        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications", json=APPLICATION_PAYLOAD
        )

        assert response.status_code == 409


class TestApplicationReviewEndpoints:
    """Tests for the manager-facing side of the queue."""

    def test_the_queue_is_listed(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """A manager sees what is waiting."""
        response = _client(applications, companies, auth).get(
            "/api/v1/hca-applications"
        )

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_the_queue_takes_no_company_parameter(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The company comes from the caller, never from the query string.

        Notes:
            A company identifier a caller supplies would let a manager read
            another agency's hiring queue by changing it.
        """
        caller = _user(company_id="company-7")
        _client(applications, companies, auth, caller).get(
            "/api/v1/hca-applications?company_id=company-1"
        )

        assert applications.list_pending.await_args.args[0] is caller

    def test_approving_answers_200_with_the_decision(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The validation step the specification requires."""
        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications/application-1/approve",
            json={"contract_type": "cdi"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == HcaApplicationStatus.APPROVED.value
        assert response.json()["hca_id"] == "hca-new"

    def test_approving_without_a_contract_is_refused(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """Nobody is employed on whichever contract sorts first."""
        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications/application-1/approve", json={}
        )

        assert response.status_code == 422
        applications.approve.assert_not_awaited()

    def test_the_contract_reaches_the_service(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """What the approver chose is what is applied."""
        _client(applications, companies, auth).post(
            "/api/v1/hca-applications/application-1/approve",
            json={"contract_type": "cdd"},
        )

        assert applications.approve.await_args.args[2] is ContractType.CDD

    def test_rejecting_answers_200(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """Declining records the decision and creates nothing."""
        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications/application-1/reject",
            json={"reason": "no availability"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == HcaApplicationStatus.REJECTED.value

    def test_another_companys_application_is_403(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The service's refusal surfaces as forbidden, not as a 500."""
        applications.approve.side_effect = MTApplicationForbidden("not yours")

        response = _client(applications, companies, auth).post(
            "/api/v1/hca-applications/application-1/approve",
            json={"contract_type": "cdi"},
        )

        assert response.status_code == 403


class TestStaffAccountEndpoints:
    """Tests for an administrator creating an account."""

    def test_creating_an_account_returns_the_temporary_password(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The administrator gets something to hand over, once."""
        response = _client(applications, companies, auth).post(
            "/api/v1/auth/accounts",
            json={
                "hca_id": "hca-1",
                "email": "new@example.com",
                "full_name": "New Starter",
            },
        )

        assert response.status_code == 201
        assert response.json()["temporary_password"] == "GeneratedPass123"
        assert response.json()["must_change_password"] is True

    def test_the_payload_cannot_choose_the_password(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The first credential is generated, not picked by a person.

        Notes:
            Letting an administrator choose it would mean the first password is
            one they typed into a ticket and probably reused across three new
            starters. There is no field for it, so there is nothing to reuse.
        """
        from models.schemas.requests.staff_account_request import StaffAccountRequest

        assert "password" not in StaffAccountRequest.model_fields

    def test_the_payload_cannot_choose_a_role(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """This route creates assistants; promotion is a separate act."""
        from models.schemas.requests.staff_account_request import StaffAccountRequest

        assert "role" not in StaffAccountRequest.model_fields

    def test_a_missing_assistant_record_is_refused(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """An account with nothing to point at cannot be checked against a plan."""
        response = _client(applications, companies, auth).post(
            "/api/v1/auth/accounts",
            json={"email": "new@example.com", "full_name": "New Starter"},
        )

        assert response.status_code == 422


class TestPasswordChangeEndpoint:
    """Tests for replacing your own password."""

    def test_a_change_answers_200_without_the_credential(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The response describes the account and never its password."""
        response = _client(applications, companies, auth).post(
            "/api/v1/auth/password",
            json={
                "current_password": "TemporaryPass123!",
                "new_password": "MyOwnPassphrase99!",
            },
        )

        assert response.status_code == 200
        assert "password" not in response.json()
        assert "MyOwnPassphrase99!" not in response.text

    def test_reusing_the_password_answers_409(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """ "Changing" it to itself is refused, not quietly accepted."""
        auth.change_password.side_effect = MTAuthSamePassword("same")

        response = _client(applications, companies, auth).post(
            "/api/v1/auth/password",
            json={
                "current_password": "TemporaryPass123!",
                "new_password": "TemporaryPass123!",
            },
        )

        assert response.status_code == 409

    def test_a_weak_new_password_is_refused(
        self, applications: AsyncMock, companies: AsyncMock, auth: AsyncMock
    ) -> None:
        """The policy applies to the mandatory change too."""
        response = _client(applications, companies, auth).post(
            "/api/v1/auth/password",
            json={"current_password": "TemporaryPass123!", "new_password": "short"},
        )

        assert response.status_code == 422
        auth.change_password.assert_not_awaited()


class TestMandatoryChangeEnforcement:
    """Tests that the forced change is enforced, not merely requested."""

    def _client_for(self, caller: User) -> TestClient:
        """Build a client whose middleware resolves a token to one account.

        Args:
            caller (User): The account every bearer token resolves to.

        Returns:
            TestClient: A client over an app carrying the real middleware.

        Notes:
            The real :class:`AuthMiddleware` is mounted and only its
            *credential lookup* is stubbed. What is under test runs after a
            valid credential has been accepted — which is the whole point: an
            account with a temporary password can sign in, and must, in order
            to replace it.
        """
        service = AsyncMock()
        service.resolve_token.return_value = caller

        @asynccontextmanager
        async def _standalone() -> AsyncIterator[AsyncMock]:
            """Stand in for the middleware's own service factory.

            Yields:
                AsyncMock: The stubbed authentication service.
            """
            yield service

        auth_middleware.get_auth_service_standalone = _standalone

        app = FastAPI()

        @app.get("/api/v1/anything")
        async def anything() -> dict:
            return {"reached": True}

        @app.post("/api/v1/auth/password")
        async def change() -> dict:
            return {"changed": True}

        app.add_middleware(AuthMiddleware)
        return TestClient(app)

    def test_an_account_needing_a_change_is_refused_everywhere_else(self) -> None:
        """A flagged account cannot use the application at all.

        Notes:
            **This is what makes the change mandatory rather than advisory.**
            Without a check at this level the account could sign in and then do
            everything else with a credential a second person typed. Enforcing
            it in the middleware rather than in each guard means a route added
            tomorrow is covered without anybody remembering to cover it.
        """
        client = self._client_for(_user(role=UserRole.HCA, must_change=True))

        response = client.get(
            "/api/v1/anything", headers={"Authorization": "Bearer token"}
        )

        assert response.status_code == 403
        assert response.json()["must_change_password"] is True

    def test_the_password_route_stays_reachable(self) -> None:
        """The one exception, without which the account could never recover."""
        client = self._client_for(_user(role=UserRole.HCA, must_change=True))

        response = client.post(
            "/api/v1/auth/password", headers={"Authorization": "Bearer token"}
        )

        assert response.status_code == 200

    def test_an_account_that_has_changed_is_not_blocked(self) -> None:
        """Clearing the flag restores ordinary use."""
        client = self._client_for(_user(role=UserRole.HCA, must_change=False))

        response = client.get(
            "/api/v1/anything", headers={"Authorization": "Bearer token"}
        )

        assert response.status_code == 200
        assert response.json() == {"reached": True}

    def test_the_refusal_names_the_reason_machine_readably(self) -> None:
        """A client has to be able to route the user to the change screen.

        Notes:
            A bare 403 is indistinguishable from "you lack the role", and a
            client that cannot tell them apart shows the wrong message to
            somebody who simply needs to set a password.
        """
        client = self._client_for(_user(role=UserRole.HCA, must_change=True))

        body = client.get(
            "/api/v1/anything", headers={"Authorization": "Bearer token"}
        ).json()

        assert body["must_change_password"] is True
        assert "password" in body["detail"].lower()


class TestPublicRouteScope:
    """Tests that the unauthenticated openings are exactly as wide as intended."""

    def test_submitting_an_application_is_public(self) -> None:
        """Somebody with no account has to be able to ask for one."""
        assert (
            AuthMiddleware(app=None)._is_exempt("/api/v1/hca-applications", "POST")
            is True
        )

    def test_reading_the_queue_is_not_public(self) -> None:
        """The hiring queue is a manager's, behind the same path.

        Notes:
            **This is the bug the method check exists to prevent, and it was a
            real one.** Exempting the prefix made ``GET /hca-applications``
            public — the whole review queue, with every applicant's name,
            address and telephone number — and it took an end-to-end run to
            notice, because the route still answered.
        """
        assert (
            AuthMiddleware(app=None)._is_exempt("/api/v1/hca-applications", "GET")
            is False
        )

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(
                "/api/v1/hca-applications/application-1", id="One application"
            ),
            pytest.param(
                "/api/v1/hca-applications/application-1/approve", id="Approving"
            ),
            pytest.param(
                "/api/v1/hca-applications/application-1/reject", id="Rejecting"
            ),
        ],
    )
    def test_deciding_an_application_is_never_public(self, path: str) -> None:
        """Approving somebody into the workforce always needs a credential.

        Args:
            path (str): The decision route to check.

        Notes:
            These are ``POST`` routes under the public path, so the exemption
            has to match *exactly* rather than by prefix — otherwise anybody
            could approve their own application.
        """
        assert AuthMiddleware(app=None)._is_exempt(path, "POST") is False

    def test_the_company_list_is_public_for_reading(self) -> None:
        """An applicant cannot choose a company without seeing the list."""
        assert (
            AuthMiddleware(app=None)._is_exempt("/api/v1/companies/choices", "GET")
            is True
        )

    def test_creating_a_company_is_not_public(self) -> None:
        """Only the choices path is open, not the company routes generally."""
        assert AuthMiddleware(app=None)._is_exempt("/api/v1/companies", "POST") is False
