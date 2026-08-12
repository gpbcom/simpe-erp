from __future__ import annotations

# Standard library imports
from decimal import Decimal

# Third-party imports
import pytest

# First-party imports
from models.organisation.companies.company import Company
from models.schemas.exceptions import (
    MTCompanyViewInvalidIbanMaskFlag,
    MTCompanyViewInvalidName,
)
from models.schemas.responses.companies.company_view import CompanyView
from tests.annotations import ModelInput

IBAN = "FR7630006000011234567890189"


def _agency() -> Company:
    """Return an agency carrying everything the view can project.

    Returns:
        Company: The agency under test.
    """
    return Company(
        id="company-1",
        name="Aide et Soins",
        legal_form="SARL",
        share_capital=Decimal("10000.50"),
        rcs_number="RCS Paris B 123 456 789",
        vat_number="FR12345678901",
        phone_number="01 23 45 67 89",
        registration_number="123456789",
        contact_email="hello@example.com",
        iban=IBAN,
        bic="BNPAFRPP",
        logo_url="https://s3.example/simple-erp/company-logos/company-1/a.png",
    )


class TestCompanyViewRevealsOnlyToAnAdministrator:
    """Tests for the projection that decides who reads a bank account."""

    def test_an_administrator_reads_the_account_whole(self) -> None:
        """The one caller entitled to it gets the number they can correct."""
        view = CompanyView.from_company(_agency(), reveal=True)

        assert view.iban == IBAN
        assert view.iban_is_masked is False

    def test_everybody_else_reads_it_masked(self) -> None:
        """A manager runs the week; they have no reason to hold the account.

        Notes:
            The assertion that matters is the negative one. Checking the
            prefix and suffix survive would pass on a view that masked nothing
            at all — what makes this a protection is that the middle is gone.
        """
        view = CompanyView.from_company(_agency(), reveal=False)

        assert view.iban is not None
        assert view.iban != IBAN
        assert IBAN[4:-4] not in view.iban
        assert view.iban_is_masked is True

    def test_an_agency_with_no_account_masks_to_nothing(self) -> None:
        """No account is ``None`` either way, not a row of bullets."""
        agency = Company(name="Aide et Soins")

        assert CompanyView.from_company(agency, reveal=False).iban is None
        assert CompanyView.from_company(agency, reveal=True).iban is None

    def test_every_other_field_survives_the_projection(self) -> None:
        """Masking the account must not quietly drop the rest of the record.

        Notes:
            The view replaces the company on two manager-facing routes, so a
            field it forgets to carry is a field that disappears from a screen
            — which reads as data loss rather than as a permission.
        """
        agency = _agency()

        view = CompanyView.from_company(agency, reveal=False)

        assert view.id == agency.id
        assert view.name == agency.name
        assert view.legal_form == agency.legal_form
        assert view.share_capital == agency.share_capital
        assert view.rcs_number == agency.rcs_number
        assert view.vat_number == agency.vat_number
        assert view.phone_number == agency.phone_number
        assert view.registration_number == agency.registration_number
        assert view.contact_email == str(agency.contact_email)
        assert view.bic == agency.bic
        assert view.logo_url == agency.logo_url
        assert view.is_accepting_applications is True

    def test_the_bic_is_not_masked(self) -> None:
        """A BIC names a bank, not an account.

        Notes:
            It identifies an institution thousands of people share. Masking it
            would cost a manager the ability to recognise the bank while
            protecting nothing.
        """
        view = CompanyView.from_company(_agency(), reveal=False)

        assert view.bic == "BNPAFRPP"


class TestCompanyViewValidation:
    """Tests for what the projection itself refuses to be built from."""

    def test_a_nameless_view_is_refused(self) -> None:
        """The trading name is what the record is recognised by."""
        with pytest.raises(MTCompanyViewInvalidName):
            CompanyView(name="   ")

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("false", id="Invalid - a truthy string"),
            pytest.param(0, id="Invalid - an integer"),
        ],
    )
    def test_a_non_boolean_mask_flag_is_refused(self, value: ModelInput) -> None:
        """A view that claimed to be masked when it was not would leak.

        Args:
            value (ModelInput): The rejected flag.
        """
        with pytest.raises(MTCompanyViewInvalidIbanMaskFlag):
            CompanyView(name="Aide et Soins", iban_is_masked=value)

    def test_the_flag_defaults_to_masked(self) -> None:
        """The safe default for a flag gating an account reveals nothing.

        Notes:
            A caller that forgets to set it under-shares rather than
            over-shares, which is the direction a mistake here should fail in.
        """
        assert CompanyView(name="Aide et Soins").iban_is_masked is True

    def test_a_masked_number_is_storable_in_the_view(self) -> None:
        """The view must accept what ``Company`` would reject.

        Notes:
            Bullets are not a valid IBAN, and re-running the model's validator
            here would make the protection unrepresentable — the projection
            could carry only numbers it was supposed to be hiding.
        """
        view = CompanyView.from_company(_agency(), reveal=False)

        assert CompanyView(name="X", iban=view.iban).iban == view.iban
        with pytest.raises(Exception):
            Company(name="X", iban=view.iban)
