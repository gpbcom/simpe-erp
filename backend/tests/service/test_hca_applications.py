from __future__ import annotations

# Standard library imports
from typing import Dict, Optional
from unittest.mock import AsyncMock

# Third-party imports
import pytest

# First-party imports
from models.auth.user import User
from models.organisation.companies.company import Company
from models.configuration.auth_config import AuthConfig
from models.enums import (
    AccountOrigin,
    ContractType,
    HcaApplicationStatus,
    UserRole,
)
from models.geo.postal_address import PostalAddress
from models.people.hca import Hca
from models.people.hca_application import HcaApplication
from service.auth.auth import AuthService
from service.companies.exceptions import (
    MTCompanyNotAcceptingApplications,
    MTCompanyNotFound,
)
from service.hcas.exceptions import (
    MTApplicationAlreadyDecided,
    MTApplicationForbidden,
    MTApplicationNotFound,
    MTDuplicateApplication,
)
from service.hcas.hcas import HcaService
from tests.annotations import ModelInput

HASH = "$2b$12$" + "a" * 53
ADDRESS = PostalAddress(
    street="9 rue Oberkampf",
    postal_code="75011",
    city="Paris",
    latitude=48.8650,
    longitude=2.3780,
)


def _user(
    role: UserRole = UserRole.MANAGER, company_id: Optional[str] = "company-1"
) -> User:
    """Build an account for a role.

    Args:
        role (UserRole): The role to grant.
        company_id (Optional[str]): The company it belongs to.

    Returns:
        User: The account.
    """
    return User(
        id=f"user-{role.value}",
        email=f"{role.value}@example.com",
        full_name="Test Account",
        role=role,
        hca_id="hca-1" if role is UserRole.HCA else None,
        company_id=company_id,
    )


def _application(**overrides: ModelInput) -> HcaApplication:
    """Build an application.

    Args:
        **overrides (ModelInput): Fields to replace.

    Returns:
        HcaApplication: The application.
    """
    values: Dict[str, ModelInput] = {
        "id": "application-1",
        "company_id": "company-1",
        "first_name": "Ana",
        "last_name": "Lopez",
        "phone_number": "+33611223344",
        "email": "ana.lopez@example.com",
        "address": ADDRESS,
        "hashed_password": HASH,
    }
    values.update(overrides)
    return HcaApplication(**values)


@pytest.fixture
def applications() -> AsyncMock:
    """Return a stand-in application repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.create.side_effect = lambda item: item.model_copy(
        update={"id": "application-1"}
    )
    repository.get.return_value = _application()
    repository.list.return_value = [_application()]
    repository.pending_for_email.return_value = None
    repository.update.side_effect = lambda item: item
    return repository


@pytest.fixture
def companies() -> AsyncMock:
    """Return a stand-in company repository, open to applications.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.get.return_value = Company(
        id="company-1", name="Aide et Soins", is_accepting_applications=True
    )
    return repository


@pytest.fixture
def hcas() -> AsyncMock:
    """Return a stand-in assistant repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.create.side_effect = lambda item: item.model_copy(
        update={"id": "hca-new"}
    )
    return repository


@pytest.fixture
def users() -> AsyncMock:
    """Return a stand-in account repository.

    Returns:
        AsyncMock: The repository double.
    """
    repository = AsyncMock()
    repository.create.side_effect = lambda item: item.model_copy(
        update={"id": "user-new"}
    )
    return repository


@pytest.fixture
def service(
    applications: AsyncMock,
    companies: AsyncMock,
    hcas: AsyncMock,
    users: AsyncMock,
) -> HcaService:
    """Return an application service over stand-in repositories.

    Args:
        applications (AsyncMock): The application repository double.
        companies (AsyncMock): The company repository double.
        hcas (AsyncMock): The assistant repository double.
        users (AsyncMock): The account repository double.

    Returns:
        HcaService: The service under test.
    """
    return HcaService(
        applications=applications,
        companies=companies,
        hcas=hcas,
        users=users,
        auth=AuthService(users=users, hcas=hcas, config=AuthConfig()),
    )


class TestSubmission:
    """Tests for an assistant applying to a company."""

    async def test_an_application_is_recorded_as_pending(
        self, service: HcaService
    ) -> None:
        """The ordinary path: nothing is granted, a queue entry is made."""
        application = await service.submit(
            company_id="company-1",
            first_name="Ana",
            last_name="Lopez",
            phone_number="+33611223344",
            email="ana.lopez@example.com",
            password="ChosenPassphrase!",
            address=ADDRESS,
        )

        assert application.status is HcaApplicationStatus.PENDING

    async def test_no_account_is_created_while_pending(
        self, service: HcaService, users: AsyncMock, hcas: AsyncMock
    ) -> None:
        """An unvetted submission is a row in a queue, not a way in.

        Notes:
            **This is the property the whole design turns on.** Creating an
            inactive account up front would put an unvetted row in the table
            every guard reads from, and one forgotten ``is_active`` check would
            let a stranger in.
        """
        await service.submit(
            company_id="company-1",
            first_name="Ana",
            last_name="Lopez",
            phone_number="+33611223344",
            email="ana.lopez@example.com",
            password="ChosenPassphrase!",
            address=ADDRESS,
        )

        users.create.assert_not_called()
        hcas.create.assert_not_called()

    async def test_the_password_is_hashed_before_it_is_stored(
        self, service: HcaService, applications: AsyncMock
    ) -> None:
        """A queued application is not a plaintext credential waiting.

        Notes:
            An application can sit for days awaiting a decision, and a
            plaintext password sitting for days is one in every backup taken
            meanwhile.
        """
        await service.submit(
            company_id="company-1",
            first_name="Ana",
            last_name="Lopez",
            phone_number="+33611223344",
            email="ana.lopez@example.com",
            password="ChosenPassphrase!",
            address=ADDRESS,
        )

        stored = applications.create.await_args.args[0]
        assert stored.hashed_password != "ChosenPassphrase!"
        assert stored.hashed_password.startswith("$2b$")

    async def test_an_unknown_company_is_refused(
        self, service: HcaService, companies: AsyncMock
    ) -> None:
        """Applying to an agency that does not exist is a 404, not a queue entry."""
        companies.get.return_value = None

        with pytest.raises(MTCompanyNotFound):
            await service.submit(
                company_id="ghost",
                first_name="Ana",
                last_name="Lopez",
                phone_number="+33611223344",
                email="ana.lopez@example.com",
                password="ChosenPassphrase!",
                address=ADDRESS,
            )

    async def test_a_closed_company_is_refused_distinctly(
        self, service: HcaService, companies: AsyncMock
    ) -> None:
        """ "Not hiring" and "does not exist" are different answers.

        Notes:
            Somebody told the agency does not exist goes looking for a typo;
            somebody told it is not hiring tries another.
        """
        companies.get.return_value = Company(
            id="company-1", name="Aide et Soins", is_accepting_applications=False
        )

        with pytest.raises(MTCompanyNotAcceptingApplications):
            await service.submit(
                company_id="company-1",
                first_name="Ana",
                last_name="Lopez",
                phone_number="+33611223344",
                email="ana.lopez@example.com",
                password="ChosenPassphrase!",
                address=ADDRESS,
            )

    async def test_a_second_application_to_one_company_is_refused(
        self, service: HcaService, applications: AsyncMock
    ) -> None:
        """One pending application per company per person."""
        applications.pending_for_email.return_value = _application()

        with pytest.raises(MTDuplicateApplication):
            await service.submit(
                company_id="company-1",
                first_name="Ana",
                last_name="Lopez",
                phone_number="+33611223344",
                email="ana.lopez@example.com",
                password="ChosenPassphrase!",
                address=ADDRESS,
            )

    async def test_the_duplicate_check_is_scoped_to_the_company(
        self, service: HcaService, applications: AsyncMock
    ) -> None:
        """Applying to two agencies at once is legitimate.

        Notes:
            A global check would refuse the second, which is somebody looking
            for work being told they may only look in one place.
        """
        await service.submit(
            company_id="company-1",
            first_name="Ana",
            last_name="Lopez",
            phone_number="+33611223344",
            email="ana.lopez@example.com",
            password="ChosenPassphrase!",
            address=ADDRESS,
        )

        assert applications.pending_for_email.await_args.args[1] == "company-1"


class TestApproval:
    """Tests for the validation step the specification requires."""

    async def test_approval_creates_the_assistant_and_the_account(
        self, service: HcaService, hcas: AsyncMock, users: AsyncMock
    ) -> None:
        """Both records appear together, or the applicant cannot work."""
        await service.approve("application-1", _user(), ContractType.CDI)

        hcas.create.assert_awaited_once()
        users.create.assert_awaited_once()

    async def test_the_new_account_need_not_change_its_password(
        self, service: HcaService, users: AsyncMock
    ) -> None:
        """The applicant chose this password themselves.

        Notes:
            The forced change exists because a second person knows the
            credential. On this path nobody else ever did, so demanding a
            change would be ceremony.
        """
        await service.approve("application-1", _user(), ContractType.CDI)

        created = users.create.await_args.args[0]
        assert created.account_origin is AccountOrigin.SELF_REGISTERED
        assert created.must_change_password is False

    async def test_the_chosen_password_carries_onto_the_account(
        self, service: HcaService, users: AsyncMock
    ) -> None:
        """The hash moves across; nothing is re-hashed or regenerated."""
        await service.approve("application-1", _user(), ContractType.CDI)

        assert users.create.await_args.args[0].hashed_password == HASH

    async def test_the_contract_comes_from_the_approver(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """An applicant states a hope; the agency states the terms.

        Notes:
            Reading it off the application would let an unauthenticated payload
            set an employment term.
        """
        await service.approve("application-1", _user(), ContractType.CDD)

        created: Hca = hcas.create.await_args.args[0]
        assert created.contract_type is ContractType.CDD

    async def test_the_new_assistant_belongs_to_the_chosen_company(
        self, service: HcaService, hcas: AsyncMock
    ) -> None:
        """The company the applicant picked is the one they join."""
        await service.approve("application-1", _user(), ContractType.CDI)

        assert hcas.create.await_args.args[0].company_id == "company-1"

    async def test_the_decision_is_attributed(self, service: HcaService) -> None:
        """Who approved somebody into the workforce is recorded."""
        decided = await service.approve("application-1", _user(), ContractType.CDI)

        assert decided.decided_by == "user-manager"
        assert decided.status is HcaApplicationStatus.APPROVED
        assert decided.hca_id == "hca-new"


class TestRejection:
    """Tests for declining an application."""

    async def test_rejection_creates_nothing(
        self, service: HcaService, hcas: AsyncMock, users: AsyncMock
    ) -> None:
        """A declined applicant leaves no assistant and no account behind."""
        await service.reject("application-1", _user(), "not enough experience")

        hcas.create.assert_not_called()
        users.create.assert_not_called()

    async def test_the_reason_is_kept(self, service: HcaService) -> None:
        """The record says why, for whoever is asked later."""
        decided = await service.reject("application-1", _user(), "no availability")

        assert decided.rejection_reason == "no availability"
        assert decided.status is HcaApplicationStatus.REJECTED


class TestDecisionAuthority:
    """Tests for who may decide which applications."""

    async def test_a_manager_decides_their_own_companys_queue(
        self, service: HcaService
    ) -> None:
        """The ordinary case works."""
        assert await service.approve(
            "application-1", _user(company_id="company-1"), ContractType.CDI
        )

    async def test_a_manager_cannot_decide_another_companys_application(
        self, service: HcaService
    ) -> None:
        """One agency has no standing over another's hiring.

        Notes:
            **Row-level, like every rule of this shape here.** A route guard
            proves the caller is a manager; it cannot tell whose queue the
            identifier in the path belongs to.
        """
        with pytest.raises(MTApplicationForbidden):
            await service.approve(
                "application-1", _user(company_id="company-2"), ContractType.CDI
            )

    async def test_a_refused_decision_creates_nothing(
        self, service: HcaService, hcas: AsyncMock, users: AsyncMock
    ) -> None:
        """The check happens before any record is written."""
        with pytest.raises(MTApplicationForbidden):
            await service.approve(
                "application-1", _user(company_id="company-2"), ContractType.CDI
            )

        hcas.create.assert_not_called()
        users.create.assert_not_called()

    async def test_an_administrator_of_another_company_may_not_decide(
        self, service: HcaService
    ) -> None:
        """Being an administrator is not the same as being *this* one.

        Notes:
            There used to be an exemption for an administrator belonging to no
            company, so the first agency could approve its first application
            before any company existed. Nothing needs it now — an agency and
            its first administrator are created by the same call — and while it
            stood, any administrator without an agency could decide every
            agency's applications. The role no longer widens the scope.
        """
        with pytest.raises(MTApplicationForbidden):
            await service.approve(
                "application-1",
                _user(role=UserRole.ADMIN, company_id="company-2"),
                ContractType.CDI,
            )

    async def test_an_administrator_of_the_owning_company_may_decide(
        self, service: HcaService
    ) -> None:
        """The agency's own administrator still decides its queue."""
        assert await service.approve(
            "application-1",
            _user(role=UserRole.ADMIN, company_id="company-1"),
            ContractType.CDI,
        )

    async def test_a_manager_cannot_read_another_companys_application(
        self, service: HcaService
    ) -> None:
        """Reading is gated the same way as deciding."""
        with pytest.raises(MTApplicationForbidden):
            await service.get_application(
                "application-1", _user(company_id="company-2")
            )

    async def test_the_queue_is_filtered_by_the_callers_company(
        self, service: HcaService, applications: AsyncMock
    ) -> None:
        """The company is taken from the caller, never from a parameter.

        Notes:
            A company identifier in the query string would let a manager read
            another agency's hiring queue by changing it.
        """
        await service.list_pending(_user(company_id="company-7"))

        assert applications.list.await_args.kwargs["company_id"] == "company-7"


class TestDecisionIdempotence:
    """Tests for the rule that an application is decided once."""

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(HcaApplicationStatus.APPROVED, id="Already approved"),
            pytest.param(HcaApplicationStatus.REJECTED, id="Already rejected"),
        ],
    )
    async def test_a_decided_application_cannot_be_approved_again(
        self,
        service: HcaService,
        applications: AsyncMock,
        status: HcaApplicationStatus,
    ) -> None:
        """A second approval would create a second person.

        Args:
            service (HcaService): The service under test.
            applications (AsyncMock): The repository double.
            status (HcaApplicationStatus): The terminal status to check.

        Notes:
            Approving twice creates a second assistant and a second account for
            one human being; rejecting an approved one strands the account the
            approval already made.
        """
        applications.get.return_value = _application(status=status, decided_by="user-1")

        with pytest.raises(MTApplicationAlreadyDecided):
            await service.approve("application-1", _user(), ContractType.CDI)

    async def test_an_absent_application_is_reported(
        self, service: HcaService, applications: AsyncMock
    ) -> None:
        """Deciding something that does not exist raises."""
        applications.get.return_value = None

        with pytest.raises(MTApplicationNotFound):
            await service.approve("ghost", _user(), ContractType.CDI)
