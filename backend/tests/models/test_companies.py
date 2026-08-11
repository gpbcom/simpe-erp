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
    MTCompanyInvalidBic,
    MTCompanyInvalidIban,
    MTCompanyInvalidLogoUrl,
    MTCompanyInvalidLegalForm,
    MTCompanyInvalidPhoneNumber,
    MTCompanyInvalidRcsNumber,
    MTCompanyInvalidShareCapital,
    MTCompanyInvalidSapDeclarationNumber,
    MTCompanyInvalidVatNumber,
    MTCompanyInvalidEmail,
    MTCompanyInvalidId,
    MTCompanyInvalidIsAcceptingApplications,
    MTCompanyInvalidName,
    MTCompanyInvalidRegistrationNumber,
    MTInvalidCompanyException,
)
from models.configuration.s3_config import S3Config


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
        assert Company(name="X", share_capital="10000.50").share_capital == Decimal(
            "10000.50"
        )

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

    def test_a_sap_declaration_number_is_normalised(self) -> None:
        """Spaces removed and letters upper-cased, like the VAT number."""
        assert (
            Company(
                name="X", sap_declaration_number="sap 123 456 789"
            ).sap_declaration_number
            == "SAP123456789"
        )

    def test_a_sap_declaration_number_is_not_pattern_checked(self) -> None:
        """**Deliberately looser than the VAT number.**

        Notes:
            The declaration number's format has changed more than once and
            varies by département. A shape check would refuse valid numbers, and
            on this field that means silently dropping the line that lets a
            customer claim their tax credit — a worse failure than storing
            something odd.
        """
        assert (
            Company(
                name="X", sap_declaration_number="SAP/2026/0042-B"
            ).sap_declaration_number
            == "SAP/2026/0042-B"
        )

    def test_an_absent_sap_declaration_number_is_allowed(self) -> None:
        """An agency that has not registered prints without the mention."""
        assert Company(name="X").sap_declaration_number is None
        assert (
            Company(name="X", sap_declaration_number="   ").sap_declaration_number
            is None
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("S" * 65, id="Invalid - longer than the column"),
            pytest.param(12345, id="Invalid - not a string"),
        ],
    )
    def test_an_unusable_sap_declaration_number_is_refused(self, value: object) -> None:
        """Length is the one thing that can be asserted without guessing.

        Args:
            value (object): The rejected value.
        """
        with pytest.raises(MTCompanyInvalidSapDeclarationNumber):
            Company(name="X", sap_declaration_number=value)

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


class TestCompanyBankingDetails:
    """Tests for the account a customer is asked to pay into."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            pytest.param(
                "FR76 3000 6000 0112 3456 7890 189",
                "FR7630006000011234567890189",
                id="Valid - grouped as a bank prints it",
            ),
            pytest.param(
                "fr7630006000011234567890189",
                "FR7630006000011234567890189",
                id="Valid - lower case",
            ),
            pytest.param(
                "DE89370400440532013000",
                "DE89370400440532013000",
                id="Valid - not French",
            ),
        ],
    )
    def test_an_iban_is_normalised_before_it_is_stored(
        self, raw: str, expected: str
    ) -> None:
        """The grouped form and the unbroken form are the same account.

        Args:
            raw (str): The number as somebody types it off a statement.
            expected (str): What is stored.

        Notes:
            Normalising on the way in is what makes two spellings of one
            account compare equal. Stored as typed, the same agency could hold
            two IBANs that differ only in spacing.
        """
        assert Company(name="X", iban=raw).iban == expected

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param(
                "FR7630006000011234567890188", id="Invalid - check digits wrong"
            ),
            pytest.param(
                "FR7630006000011234567809189", id="Invalid - two digits transposed"
            ),
            pytest.param("FR76", id="Invalid - too short"),
            pytest.param("7630006000011234567890189", id="Invalid - no country code"),
            pytest.param("F" * 40, id="Invalid - longer than any IBAN"),
            pytest.param(12345, id="Invalid - not a string"),
        ],
    )
    def test_an_unusable_iban_is_refused(self, value: Any) -> None:
        """A wrong account number must fail here, not at the bank.

        Args:
            value (Any): The rejected value.

        Notes:
            The transposition case is the one that matters. It satisfies every
            shape rule and fails only the checksum — which is exactly the error
            a human makes copying twenty-seven characters by hand, and exactly
            what the two check digits exist to catch.
        """
        with pytest.raises(MTCompanyInvalidIban):
            Company(name="X", iban=value)

    @pytest.mark.parametrize(
        "value", [pytest.param(None, id="None"), pytest.param("  ", id="Blank")]
    )
    def test_no_account_is_none_rather_than_empty(self, value: Optional[str]) -> None:
        """An untouched form field must not become a stored empty string.

        Args:
            value (Optional[str]): The absent value.
        """
        assert Company(name="X", iban=value).iban is None
        assert Company(name="X", bic=value).bic is None

    @pytest.mark.parametrize(
        "raw,expected",
        [
            pytest.param("bnpafrpp", "BNPAFRPP", id="Valid - eight characters"),
            pytest.param("BNPA FR PP XXX", "BNPAFRPPXXX", id="Valid - with a branch"),
        ],
    )
    def test_a_bic_is_normalised(self, raw: str, expected: str) -> None:
        """Eight or eleven characters, upper-cased and unspaced.

        Args:
            raw (str): The code as typed.
            expected (str): What is stored.
        """
        assert Company(name="X", bic=raw).bic == expected

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("BNPAFRP", id="Invalid - seven characters"),
            pytest.param("BNPAFRPPXX", id="Invalid - ten characters"),
            pytest.param("1NPAFRPP", id="Invalid - digit in the bank code"),
            pytest.param(99, id="Invalid - not a string"),
        ],
    )
    def test_an_unusable_bic_is_refused(self, value: Any) -> None:
        """A BIC has two lengths and no others.

        Args:
            value (Any): The rejected value.
        """
        with pytest.raises(MTCompanyInvalidBic):
            Company(name="X", bic=value)

    def test_a_bic_is_not_required_alongside_an_iban(self) -> None:
        """Inside SEPA the IBAN alone routes the transfer.

        Notes:
            Deliberately not a conditional rule. Demanding a BIC would refuse a
            complete answer for missing something the payment does not need.
        """
        company = Company(name="X", iban="FR7630006000011234567890189")

        assert company.iban is not None
        assert company.bic is None

    def test_masking_keeps_the_country_and_the_last_four(self) -> None:
        """Enough to recognise the account, not enough to pay into it.

        Notes:
            The same trade a bank statement makes. A manager checking which
            account is on file can, somebody reading over their shoulder
            cannot.
        """
        company = Company(name="X", iban="FR7630006000011234567890189")

        masked = company.masked_iban()

        assert masked is not None
        assert masked.startswith("FR76")
        assert masked.endswith("0189")
        assert "300060000112345678" not in masked
        assert len(masked) == len(company.iban or "")

    def test_masking_an_absent_account_yields_nothing(self) -> None:
        """No account is ``None``, not a row of bullets."""
        assert Company(name="X").masked_iban() is None


class TestCompanyVisualIdentity:
    """Tests for the logo an agency prints on its documents."""

    def test_a_logo_this_application_stored_is_accepted(self) -> None:
        """A URL under the logo prefix is one the object store can own."""
        url = "https://s3.example/simple-erp/company-logos/c-1/abc.png"

        assert Company(name="X", logo_url=url).logo_url == url

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("https://evil.example/tracker.png", id="Invalid - elsewhere"),
            pytest.param(
                "https://s3.example/simple-erp/hca-photos/h-1/a.png",
                id="Invalid - the photo prefix, not the logo one",
            ),
            pytest.param("ftp://s3.example/company-logos/a.png", id="Invalid - scheme"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_a_logo_from_anywhere_else_is_refused(self, value: Any) -> None:
        """The prefix check is what stops a third-party URL being stored.

        Args:
            value (Any): The rejected value.

        Notes:
            The logo is rendered on every screen and on the quote, so a remote
            one would report every viewer to whoever hosts it — and the object
            store could not own the object it is later asked to remove.
        """
        with pytest.raises(MTCompanyInvalidLogoUrl):
            Company(name="X", logo_url=value)

    @pytest.mark.parametrize(
        "value", [pytest.param(None, id="None"), pytest.param("  ", id="Blank")]
    )
    def test_no_logo_is_none(self, value: Optional[str]) -> None:
        """An agency without a logo carries ``None``, not an empty string.

        Args:
            value (Optional[str]): The absent value.
        """
        assert Company(name="X", logo_url=value).logo_url is None

    def test_the_model_prefix_matches_the_configured_one(self) -> None:
        """The two copies of the prefix must not drift.

        Notes:
            The model cannot read configuration, so it carries its own copy of
            the prefix — exactly as ``PortraitHolder`` does. Asserting they are
            equal is what keeps a change to one from silently rejecting every
            URL the other writes.
        """
        assert Company.LOGO_KEY_PREFIX == S3Config.DEFAULT_LOGO_KEY_PREFIX

    def test_the_new_leaves_share_the_company_base(self) -> None:
        """One except clause still catches everything this model raises."""
        for exception in (
            MTCompanyInvalidIban,
            MTCompanyInvalidBic,
            MTCompanyInvalidLogoUrl,
        ):
            assert issubclass(exception, MTInvalidCompanyException)


class TestTheAgencyLegalIdentifier:
    """Tests for the identifier a structured invoice is routed on."""

    @pytest.mark.parametrize(
        ("registration", "expected"),
        [
            pytest.param("12345678900019", "123456789", id="From a SIRET"),
            pytest.param("123 456 789 00019", "123456789", id="Spaced SIRET"),
            pytest.param("123456789", "123456789", id="Already a SIREN"),
            pytest.param(None, None, id="Invalid - nothing recorded"),
            pytest.param("RCS PARIS 1234", None, id="Invalid - not digits"),
            pytest.param("1234567", None, id="Invalid - neither length"),
        ],
    )
    def test_the_siren_is_read_out_of_the_registration_number(
        self, registration: object, expected: object
    ) -> None:
        """**Derived, never stored twice.**

        Notes:
            A SIRET is a SIREN plus an establishment code, so a second column
            would be a second copy of the same nine digits — free to disagree
            with the first the day somebody corrects one of them. Anything
            unreadable answers ``None`` rather than guessing: a wrong identifier
            is an invoice delivered to another company.
        """
        company = Company(
            name="Aide et Présence Paris",
            registration_number=registration,
            address={
                "street": "1 rue des Lilas",
                "postal_code": "75011",
                "city": "Paris",
                "latitude": 48.85,
                "longitude": 2.35,
            },
        )

        assert company.siren() == expected
