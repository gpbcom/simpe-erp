from __future__ import annotations

# Standard library imports
from typing import Dict, Optional, Union

# Third-party imports
import pytest

from models.auth.exceptions import (
    MTUserInvalidMustChangePassword,
    MTUserStaffAccountNeedsChange,
)
from models.auth.user import User

# First-party imports
from models.enums import AccountOrigin, HcaApplicationStatus, UserRole
from models.people.hca_application.exceptions import (
    MTHcaApplicationInvalidCompany,
    MTHcaApplicationInvalidDecision,
    MTHcaApplicationInvalidEmail,
    MTHcaApplicationInvalidName,
    MTHcaApplicationInvalidPasswordHash,
    MTHcaApplicationInvalidStatus,
    MTInvalidHcaApplicationException,
)
from models.people.hca_application import HcaApplication
from tests.annotations import ModelInput

HASH = "$2b$12$" + "a" * 53


def _kwargs(**overrides: ModelInput) -> Dict[str, ModelInput]:
    """Return the arguments for a valid application.

    Args:
        **overrides (ModelInput): Fields to replace.

    Returns:
        Dict[str, ModelInput]: Constructor keyword arguments.
    """
    base = {
        "company_id": "company-1",
        "first_name": "Ana",
        "last_name": "Lopez",
        "phone_number": "+33611223344",
        "email": "ana.lopez@example.com",
        "address": {
            "street": "9 rue Oberkampf",
            "postal_code": "75011",
            "city": "Paris",
        },
        "hashed_password": HASH,
    }
    base.update(overrides)
    return base


class TestHcaApplication:
    """Tests for an assistant's self-submitted application."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_new_application_is_pending(self) -> None:
        """Nothing is granted until somebody decides."""
        application = HcaApplication(**_kwargs())

        assert application.status is HcaApplicationStatus.PENDING
        assert application.is_pending() is True
        assert application.hca_id is None

    def test_the_full_name_is_composed(self) -> None:
        """The display name comes from the two parts."""
        assert HcaApplication(**_kwargs()).full_name() == "Ana Lopez"

    # ------------------------------------------------------------------ #
    #  company validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace"),
            pytest.param(None, id="Invalid - missing"),
        ],
    )
    def test_an_application_to_nobody_is_refused(self, value: Optional[str]) -> None:
        """The specification requires the applicant to choose a company.

        Args:
            value (Optional[str]): The rejected company identifier.

        Notes:
            An application addressed to nobody has nobody with standing to
            approve it, and would sit in the queue for ever.
        """
        with pytest.raises(MTHcaApplicationInvalidCompany):
            HcaApplication(**_kwargs(company_id=value))

    # ------------------------------------------------------------------ #
    #  email and names
    # ------------------------------------------------------------------ #

    def test_the_email_is_lower_cased(self) -> None:
        """This address becomes the sign-in, and sign-ins are lower-cased.

        Notes:
            An account stored with different capitalisation than the one typed
            at the login screen is an account nobody can reach.
        """
        application = HcaApplication(**_kwargs(email="Ana.LOPEZ@Example.com"))

        assert application.email == "ana.lopez@example.com"

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param("first_name", id="Invalid - no given name"),
            pytest.param("last_name", id="Invalid - no family name"),
        ],
    )
    def test_a_nameless_applicant_is_refused(self, field: str) -> None:
        """Both names are required.

        Args:
            field (str): The name field to blank.
        """
        with pytest.raises(MTHcaApplicationInvalidName):
            HcaApplication(**_kwargs(**{field: "  "}))

    def test_a_blank_email_is_refused(self) -> None:
        """An application with no address cannot become an account."""
        with pytest.raises(MTHcaApplicationInvalidEmail):
            HcaApplication(**_kwargs(email="   "))

    # ------------------------------------------------------------------ #
    #  The credential
    # ------------------------------------------------------------------ #

    def test_a_credential_is_required(self) -> None:
        """An application with no password could never become an account."""
        with pytest.raises(MTHcaApplicationInvalidPasswordHash):
            HcaApplication(**_kwargs(hashed_password=""))

    def test_the_credential_is_not_echoed_in_the_error(self) -> None:
        """A rejected credential does not appear in the message.

        Notes:
            Every other validator here names the offending value. This one
            deliberately does not: the message ends up in a log, and the value
            is a password.
        """
        with pytest.raises(MTHcaApplicationInvalidPasswordHash) as raised:
            HcaApplication(**_kwargs(hashed_password="   "))

        assert "   " not in str(raised.value).replace("hashed_password", "")

    # ------------------------------------------------------------------ #
    #  status and the decision record
    # ------------------------------------------------------------------ #

    def test_an_unknown_status_is_refused(self) -> None:
        """Only the three real states exist."""
        with pytest.raises(MTHcaApplicationInvalidStatus):
            HcaApplication(**_kwargs(status="maybe"))

    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(HcaApplicationStatus.APPROVED, id="Approved"),
            pytest.param(HcaApplicationStatus.REJECTED, id="Rejected"),
        ],
    )
    def test_a_decided_application_must_name_its_decider(
        self, status: HcaApplicationStatus
    ) -> None:
        """Approving somebody into the workforce is an accountable act.

        Args:
            status (HcaApplicationStatus): The terminal status to check.

        Notes:
            An approved application with nobody's name against it is a hole in
            the audit trail exactly where it matters, and refusing to build one
            is the only way to keep it from being written.
        """
        with pytest.raises(MTHcaApplicationInvalidDecision):
            HcaApplication(**_kwargs(status=status))

    def test_a_decided_application_with_a_decider_is_accepted(self) -> None:
        """The ordinary approval path works."""
        application = HcaApplication(
            **_kwargs(
                status=HcaApplicationStatus.APPROVED,
                decided_by="user-1",
                hca_id="hca-1",
            )
        )

        assert application.is_pending() is False
        assert application.status.is_terminal() is True

    def test_a_pending_application_needs_no_decider(self) -> None:
        """The requirement applies only once a decision exists."""
        assert HcaApplication(**_kwargs()).decided_by is None

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception",
        [
            pytest.param(MTHcaApplicationInvalidCompany, id="company"),
            pytest.param(MTHcaApplicationInvalidName, id="name"),
            pytest.param(MTHcaApplicationInvalidEmail, id="email"),
            pytest.param(MTHcaApplicationInvalidPasswordHash, id="credential"),
            pytest.param(MTHcaApplicationInvalidStatus, id="status"),
            pytest.param(MTHcaApplicationInvalidDecision, id="decision"),
        ],
    )
    def test_every_leaf_shares_one_base(self, exception: type) -> None:
        """One except clause catches everything this model raises.

        Args:
            exception (type): The leaf exception to check.
        """
        assert issubclass(exception, MTInvalidHcaApplicationException)


class TestStaffCreatedAccount:
    """Tests for the invariant behind the mandatory password change."""

    def test_a_staff_account_must_change_its_password(self) -> None:
        """The specification's "MANDATORY" is a construction-time invariant.

        Notes:
            **This is the rule, expressed where it cannot be forgotten.** An
            account whose password was typed by somebody else is a credential
            two people know; a flag that the next admin screen might leave off
            is not a requirement.
        """
        with pytest.raises(MTUserStaffAccountNeedsChange):
            User(
                company_id="company-1",
                email="new@example.com",
                full_name="New Starter",
                hashed_password=HASH,
                role=UserRole.HCA,
                hca_id="hca-1",
                account_origin=AccountOrigin.CREATED_BY_STAFF,
                must_change_password=False,
            )

    def test_a_staff_account_that_must_change_is_accepted(self) -> None:
        """The correct combination builds."""
        user = User(
            company_id="company-1",
            email="new@example.com",
            full_name="New Starter",
            hashed_password=HASH,
            role=UserRole.HCA,
            hca_id="hca-1",
            account_origin=AccountOrigin.CREATED_BY_STAFF,
            must_change_password=True,
        )

        assert user.must_change_password is True

    def test_a_self_registered_account_need_not_change(self) -> None:
        """Somebody who chose their own password has nothing to replace.

        Notes:
            The forced change exists because a second person knows the
            credential. On this path nobody else ever did.
        """
        user = User(
            company_id="company-1",
            email="ana@example.com",
            full_name="Ana Lopez",
            hashed_password=HASH,
            role=UserRole.HCA,
            hca_id="hca-1",
            account_origin=AccountOrigin.SELF_REGISTERED,
        )

        assert user.must_change_password is False

    def test_a_staff_account_without_a_credential_yet_is_allowed(self) -> None:
        """An account being assembled has nothing to change.

        Notes:
            The invariant fires on the combination, not on the origin alone —
            otherwise a half-built record could not exist even momentarily.
        """
        user = User.model_validate(
            {
                "email": "new@example.com",
                "full_name": "New Starter",
                "role": UserRole.HCA,
                "hca_id": "hca-1",
                "company_id": "company-1",
                "account_origin": AccountOrigin.CREATED_BY_STAFF,
            }
        )

        assert user.hashed_password is None

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("false", id="Invalid - a truthy string"),
            pytest.param(1, id="Invalid - an integer"),
        ],
    )
    def test_a_non_boolean_flag_is_refused(self, value: Union[str, int]) -> None:
        """``"false"`` is truthy, and this flag decides who can act.

        Args:
            value (Union[str, int]): The rejected flag.

        Notes:
            Read the wrong way round it either locks somebody out of their own
            account or waives the change the flag exists to force.

            The exception is named outright. This used to assert
            ``MTInvalidHcaApplicationException.__base__``, which was a
            roundabout spelling of ``Exception`` — it passed for any failure
            whatsoever, including one raised by a field this test does not
            touch, and it broke the moment the people exceptions were given a
            shared root of their own.
        """
        with pytest.raises(MTUserInvalidMustChangePassword):
            User(
                company_id="company-1",
                email="a@example.com",
                full_name="A",
                role=UserRole.MANAGER,
                must_change_password=value,
            )
