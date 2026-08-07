from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import Any, Optional, Union

# Third-party imports
import pytest

# First-party imports
from models.companies.company import Company
from models.companies.company_choice import CompanyChoice
from models.companies.exceptions import (
    MTCompanyInvalidLegalForm,
    MTCompanyInvalidPhoneNumber,
    MTCompanyInvalidRcsNumber,
    MTCompanyInvalidShareCapital,
    MTCompanyInvalidVatNumber,
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
        self, value: str, expected: Optional[str]
    ) -> None:
        """Two spellings of one number are one number.

        Args:
            value (str): The number as typed.
            expected (Optional[str]): What should be stored.

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


class TestCompanyLegalIdentity:
    """Tests for what an agency must be able to say about itself on a quote."""

    def test_every_legal_field_is_optional(self) -> None:
        """An agency that has not filled them in is still an agency.

        Notes:
            All five arrived after the rows did and none has a safe default —
            a share capital invented as zero would be a false declaration.
            The quote prints only the parts that are set.
        """
        company = Company(name="Aide et Presence")

        assert company.legal_form is None
        assert company.share_capital is None
        assert company.rcs_number is None
        assert company.vat_number is None
        assert company.phone_number is None

    def test_a_complete_legal_identity_is_accepted(self) -> None:
        """The ordinary case: everything a French quote must carry."""
        company = Company(
            name="Aide et Presence Paris",
            legal_form="SARL",
            share_capital="10000.50",
            rcs_number="RCS Paris B 123 456 789",
            vat_number="FR12345678901",
            phone_number="01 23 45 67 89",
        )

        assert company.legal_form == "SARL"
        assert company.share_capital == Decimal("10000.50")
        assert company.vat_number == "FR12345678901"

    def test_a_share_capital_keeps_its_cents(self) -> None:
        """A Decimal built from the string form, not a float.

        Notes:
            ``10000.50`` as a float is not ``10000.50``, and the difference
            reaches a document the customer is asked to sign.
        """
        assert Company(
            name="X", share_capital="10000.50"
        ).share_capital == Decimal("10000.50")

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param("lots", id="Invalid - not a number"),
        ],
    )
    def test_an_unusable_share_capital_is_refused(self, value: Any) -> None:
        """A company with no capital declares nothing, not zero.

        Args:
            value (Any): The rejected capital.
        """
        with pytest.raises(MTCompanyInvalidShareCapital):
            Company(name="X", share_capital=value)

    def test_a_vat_number_is_normalised(self) -> None:
        """Spaces removed and letters upper-cased, so it round-trips.

        Notes:
            Somebody reading it off a letterhead types ``fr 123 456 789 01``.
            Storing that verbatim would make two spellings of one number.
        """
        assert (
            Company(name="X", vat_number="fr 123 456 789 01").vat_number
            == "FR12345678901"
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("FR123", id="Invalid - too short"),
            pytest.param("FR123456789012", id="Invalid - too long"),
            pytest.param("123456789012", id="Invalid - no country code"),
        ],
    )
    def test_a_malformed_vat_number_is_refused(self, value: str) -> None:
        """**Checked, not merely stored.**

        Args:
            value (str): The rejected number.

        Notes:
            This appears on every quote, and one with a digit missing is the
            kind of error nobody notices until an accountant does.
        """
        with pytest.raises(MTCompanyInvalidVatNumber):
            Company(name="X", vat_number=value)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            pytest.param("legal_form", "   ", id="legal form of spaces"),
            pytest.param("rcs_number", "", id="empty RCS entry"),
            pytest.param("phone_number", "  ", id="phone of spaces"),
            pytest.param("vat_number", "  ", id="VAT of spaces"),
        ],
    )
    def test_a_blank_label_becomes_none(self, field: str, value: str) -> None:
        """Blank is absent, not an empty string.

        Args:
            field (str): The field being cleared.
            value (str): The blank value.

        Notes:
            The quote joins the parts that are set with a middle dot. An empty
            string would print a stray separator on a legal document.
        """
        assert getattr(Company(name="X", **{field: value}), field) is None

    def test_an_rcs_entry_reports_itself_rather_than_a_legal_form(self) -> None:
        """One rule, two exceptions, because the status map is keyed on class.

        Notes:
            The check is identical for both labels, but a rejected RCS entry
            has to say so — reporting it as a bad legal form would send an
            administrator to the wrong field.
        """
        with pytest.raises(MTCompanyInvalidRcsNumber):
            Company(name="X", rcs_number="R" * 200)
        with pytest.raises(MTCompanyInvalidLegalForm):
            Company(name="X", legal_form="S" * 200)

    def test_every_leaf_shares_one_base(self) -> None:
        """One except clause catches everything this model raises."""
        for exception in (
            MTCompanyInvalidLegalForm,
            MTCompanyInvalidShareCapital,
            MTCompanyInvalidRcsNumber,
            MTCompanyInvalidVatNumber,
            MTCompanyInvalidPhoneNumber,
        ):
            assert issubclass(exception, MTInvalidCompanyException)
