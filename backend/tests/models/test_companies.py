from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
import pytest

# First-party imports
from models.companies.company import Company
from models.companies.company_choice import CompanyChoice
from models.companies.exceptions import (
    MTCompanyInvalidEmail,
    MTCompanyInvalidId,
    MTCompanyInvalidIsAcceptingApplications,
    MTCompanyInvalidName,
    MTCompanyInvalidRegistrationNumber,
    MTInvalidCompanyException,
)


class TestCompany:
    """Tests for the agency an assistant applies to."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_name_alone_is_enough(self) -> None:
        """Everything but the trading name is optional."""
        company = Company(name="Aide et Soins")

        assert company.name == "Aide et Soins"
        assert company.is_accepting_applications is True

    def test_a_new_company_accepts_applications(self) -> None:
        """A company registered today is open to applicants.

        Notes:
            The alternative default would create every agency invisible, and
            the first applicant would be told nobody is hiring.
        """
        assert Company(name="Aide et Soins").is_accepting_applications is True

    # ------------------------------------------------------------------ #
    #  name validation
    # ------------------------------------------------------------------ #

    def test_the_name_is_trimmed(self) -> None:
        """Surrounding space is not part of a trading name."""
        assert Company(name="  Aide et Soins  ").name == "Aide et Soins"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace"),
            pytest.param(None, id="Invalid - missing"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_a_nameless_company_is_refused(self, value: Union[str, int, None]) -> None:
        """The name is the one field an applicant sees.

        Args:
            value (Union[str, int, None]): The rejected name.

        Notes:
            A company with no name is an unlabelled option in a list somebody
            has to choose from.
        """
        with pytest.raises(MTCompanyInvalidName):
            Company(name=value)

    def test_an_overlong_name_is_refused(self) -> None:
        """The bound matches the column, so a store write cannot truncate."""
        with pytest.raises(MTCompanyInvalidName):
            Company(name="x" * (Company.MAX_NAME_LENGTH + 1))

    # ------------------------------------------------------------------ #
    #  registration number validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("123 456 789", "123456789", id="Spaces removed"),
            pytest.param("123-456-789", "123456789", id="Hyphens removed"),
            pytest.param("ab12cd", "AB12CD", id="Upper-cased"),
            pytest.param("   ", None, id="Blank becomes none"),
        ],
    )
    def test_the_registration_number_is_normalised(
        self, value: str, expected: Union[str, None]
    ) -> None:
        """Two spellings of one number are one number.

        Args:
            value (str): The number as typed.
            expected (Union[str, None]): What should be stored.

        Notes:
            Registration numbers get copied off letterheads by hand, and the
            spacing varies with who is reading.
        """
        assert Company(name="A", registration_number=value).registration_number == (
            expected
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("123/456", id="Invalid - a slash"),
            pytest.param("12 34!", id="Invalid - punctuation"),
            pytest.param(123456, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_registration_number_is_refused(
        self, value: Union[str, int]
    ) -> None:
        """Only letters and digits survive normalisation.

        Args:
            value (Union[str, int]): The rejected number.
        """
        with pytest.raises(MTCompanyInvalidRegistrationNumber):
            Company(name="A", registration_number=value)

    # ------------------------------------------------------------------ #
    #  contact email validation
    # ------------------------------------------------------------------ #

    def test_the_contact_address_is_lower_cased(self) -> None:
        """Addresses are compared case-insensitively everywhere else too."""
        company = Company(name="A", contact_email="Hello@Example.COM")

        assert company.contact_email == "hello@example.com"

    def test_an_empty_contact_address_is_refused(self) -> None:
        """A blank address looks like a contact and is not one."""
        with pytest.raises(MTCompanyInvalidEmail):
            Company(name="A", contact_email="  ")

    # ------------------------------------------------------------------ #
    #  accepting-applications validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("false", id="Invalid - a truthy string"),
            pytest.param(0, id="Invalid - an integer"),
            pytest.param("no", id="Invalid - a word"),
        ],
    )
    def test_a_non_boolean_accepting_flag_is_refused(
        self, value: Union[str, int]
    ) -> None:
        """``"false"`` is truthy, and that is the whole problem.

        Args:
            value (Union[str, int]): The rejected flag.

        Notes:
            A company told to stop accepting applications, that silently kept
            accepting them, would be discovered by the applications arriving.
        """
        with pytest.raises(MTCompanyInvalidIsAcceptingApplications):
            Company(name="A", is_accepting_applications=value)

    def test_an_empty_identifier_is_refused(self) -> None:
        """An identifier that is present but blank is a bug, not a new record."""
        with pytest.raises(MTCompanyInvalidId):
            Company(id="   ", name="A")

    # ------------------------------------------------------------------ #
    #  The public projection
    # ------------------------------------------------------------------ #

    def test_the_public_choice_carries_only_a_name(self) -> None:
        """What an applicant sees cannot include the registered office.

        Notes:
            **This is the protection on an unauthenticated endpoint.** The
            company list is served without a credential, so the shape of what
            it returns is what stops an agency directory — addresses, contact
            addresses, registration numbers — being published to anybody who
            asks.
        """
        company = Company(
            id="company-1",
            name="Aide et Soins",
            registration_number="123456789",
            contact_email="hello@example.com",
            address={
                "street": "1 rue Secret",
                "postal_code": "75001",
                "city": "Paris",
            },
        )

        choice = company.to_public_choice()

        assert set(CompanyChoice.model_fields) == {"id", "name"}
        assert choice.name == "Aide et Soins"
        assert choice.id == "company-1"

    def test_an_unstored_company_projects_an_empty_identifier(self) -> None:
        """A company with no identifier yet still projects, rather than raising."""
        assert Company(name="A").to_public_choice().id == ""

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception",
        [
            pytest.param(MTCompanyInvalidId, id="id"),
            pytest.param(MTCompanyInvalidName, id="name"),
            pytest.param(MTCompanyInvalidRegistrationNumber, id="registration"),
            pytest.param(MTCompanyInvalidEmail, id="email"),
            pytest.param(MTCompanyInvalidIsAcceptingApplications, id="accepting"),
        ],
    )
    def test_every_leaf_shares_one_base(self, exception: type) -> None:
        """One except clause catches everything this model raises.

        Args:
            exception (type): The leaf exception to check.
        """
        assert issubclass(exception, MTInvalidCompanyException)

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_it_round_trips(self) -> None:
        """A dumped company rebuilds identically."""
        company = Company(
            id="company-1",
            name="Aide et Soins",
            registration_number="123456789",
            is_accepting_applications=False,
        )
        rebuilt = Company.model_validate(company.model_dump())

        assert rebuilt.name == "Aide et Soins"
        assert rebuilt.registration_number == "123456789"
        assert rebuilt.is_accepting_applications is False
