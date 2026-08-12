from __future__ import annotations

# Third-party imports
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTCompanyRegistrationRequestInvalidCompanyName,
    MTCompanyRegistrationRequestInvalidEmail,
    MTCompanyRegistrationRequestInvalidFullName,
    MTCompanyRegistrationRequestInvalidPassword,
    MTCompanyRegistrationRequestInvalidRegistrationNumber,
)
from models.schemas.requests.companies.company_registration_request import (
    CompanyRegistrationRequest,
)
from tests.annotations import ModelInput

GOOD_PASSWORD = "a-founder-password-2026"


def _payload(**overrides: ModelInput) -> dict:
    """Build a valid payload, with fields replaced.

    Args:
        **overrides (ModelInput): Fields to replace.

    Returns:
        dict: The payload.
    """
    payload = {
        "company_name": "Aide et Presence Lyon",
        "full_name": "Camille Fournier",
        "email": "camille@aide-lyon.fr",
        "password": GOOD_PASSWORD,
    }
    payload.update(overrides)
    return payload


class TestCompanyRegistrationRequestShape:
    """Tests for what the payload accepts and normalises."""

    def test_a_complete_payload_is_accepted(self) -> None:
        """The ordinary case."""
        request = CompanyRegistrationRequest(**_payload())

        assert request.company_name == "Aide et Presence Lyon"
        assert request.email == "camille@aide-lyon.fr"

    def test_the_registration_number_is_optional(self) -> None:
        """An agency being founded may not have been registered yet.

        Notes:
            Requiring it would put the paperwork before the product: somebody
            who has decided to start an agency cannot enter a number they have
            not been issued.
        """
        request = CompanyRegistrationRequest(**_payload())

        assert request.registration_number is None

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        """A pasted name does not become a different agency."""
        request = CompanyRegistrationRequest(
            **_payload(company_name="  Aide Lyon  ", full_name="  Camille  ")
        )

        assert request.company_name == "Aide Lyon"
        assert request.full_name == "Camille"

    def test_the_address_is_lower_cased(self) -> None:
        """The address a founder signs in with does not depend on their caps."""
        request = CompanyRegistrationRequest(**_payload(email="  Camille@AIDE.FR "))

        assert request.email == "camille@aide.fr"


class TestCompanyRegistrationRequestPrivilege:
    """Tests for the fields this payload must never carry.

    Notes:
        This is the one unauthenticated payload whose author is granted an
        administrator role. Everything here guards the reason that is safe: the
        role is decided by the route, and the company is always a new one.
    """

    def test_a_role_in_the_payload_is_ignored(self) -> None:
        """Naming a role does not grant it, because there is no such field.

        Notes:
            The same mistake as the ``role`` field ``RegisterRequest`` used to
            carry: a role honoured from an unauthenticated payload is a role
            granted to whoever asks for it.
        """
        request = CompanyRegistrationRequest(**_payload(role="admin"))

        assert not hasattr(request, "role")

    def test_a_company_id_in_the_payload_is_ignored(self) -> None:
        """Naming an existing agency does not attach the founder to it.

        Notes:
            A ``company_id`` honoured here would turn founding an agency into
            taking over somebody else's, since the founder is made its
            administrator.
        """
        request = CompanyRegistrationRequest(**_payload(company_id="company-1"))

        assert not hasattr(request, "company_id")

    def test_an_hca_id_in_the_payload_is_ignored(self) -> None:
        """A founder is not an assistant, and cannot claim to be one."""
        request = CompanyRegistrationRequest(**_payload(hca_id="hca-1"))

        assert not hasattr(request, "hca_id")


class TestCompanyRegistrationRequestValidation:
    """Tests for the fields it refuses."""

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="Refused - empty"),
            pytest.param("   ", id="Refused - whitespace"),
            pytest.param(None, id="Refused - missing"),
            pytest.param(42, id="Refused - not a string"),
        ],
    )
    def test_a_company_needs_a_name(self, value: ModelInput) -> None:
        """An agency without a name cannot be told apart from another.

        Args:
            value (ModelInput): The name to refuse.
        """
        with pytest.raises(MTCompanyRegistrationRequestInvalidCompanyName):
            CompanyRegistrationRequest(**_payload(company_name=value))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="Refused - empty"),
            pytest.param("   ", id="Refused - whitespace"),
            pytest.param(None, id="Refused - missing"),
        ],
    )
    def test_a_founder_needs_a_name(self, value: ModelInput) -> None:
        """The display name is what a manager screen shows.

        Args:
            value (ModelInput): The name to refuse.
        """
        with pytest.raises(MTCompanyRegistrationRequestInvalidFullName):
            CompanyRegistrationRequest(**_payload(full_name=value))

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="Refused - empty"),
            pytest.param("   ", id="Refused - whitespace"),
            pytest.param(None, id="Refused - missing"),
        ],
    )
    def test_a_founder_needs_an_address(self, value: ModelInput) -> None:
        """The address is the credential; there is no account without one.

        Args:
            value (ModelInput): The address to refuse.
        """
        with pytest.raises(MTCompanyRegistrationRequestInvalidEmail):
            CompanyRegistrationRequest(**_payload(email=value))

    def test_a_blank_registration_number_is_refused(self) -> None:
        """Absent is ``None``; blank is a mistake worth naming.

        Notes:
            Accepting ``"  "`` would store an agency whose registration number
            is neither absent nor usable, which no screen can render honestly.
        """
        with pytest.raises(MTCompanyRegistrationRequestInvalidRegistrationNumber):
            CompanyRegistrationRequest(**_payload(registration_number="   "))

    def test_a_short_password_is_refused(self) -> None:
        """The founder's account is the most privileged one the agency has."""
        with pytest.raises(MTCompanyRegistrationRequestInvalidPassword):
            CompanyRegistrationRequest(**_payload(password="short"))

    def test_a_password_beyond_what_bcrypt_hashes_is_refused(self) -> None:
        """Accepting it would be accepting only its first 72 bytes.

        Notes:
            bcrypt ignores anything past 72 bytes silently, so a longer
            password would appear to work while its tail never mattered — the
            holder could change that tail and still sign in.
        """
        with pytest.raises(MTCompanyRegistrationRequestInvalidPassword):
            CompanyRegistrationRequest(**_payload(password="a" * 73))

    def test_the_password_length_is_measured_in_bytes(self) -> None:
        """An accented password reaches the limit sooner than it looks.

        Notes:
            Seventy-two characters that encode to more than seventy-two bytes
            are past what bcrypt will hash, however short the string looks.
        """
        with pytest.raises(MTCompanyRegistrationRequestInvalidPassword):
            CompanyRegistrationRequest(**_payload(password="é" * 72))

    def test_the_password_is_never_echoed_in_the_error(self) -> None:
        """A refusal must not put the credential in the logs."""
        with pytest.raises(MTCompanyRegistrationRequestInvalidPassword) as refusal:
            CompanyRegistrationRequest(**_payload(password="secret"))

        assert "secret" not in str(refusal.value)
