from __future__ import annotations

# Standard library imports
from datetime import datetime, timezone

# Third-party imports
import pytest

# First-party imports
from models.enums import AgencyType
from models.geo.postal_address import PostalAddress
from models.organisation.agency import Agency
from models.organisation.companies.company import Company
from models.organisation.agency.exceptions import (
    MTAgencyInvalidAddress,
    MTAgencyInvalidCompanyId,
    MTAgencyInvalidDate,
    MTAgencyInvalidId,
    MTAgencyInvalidName,
    MTAgencyInvalidType,
    MTAgencyLegalIdentityMisplaced,
)
from tests.annotations import ModelInput


def _address() -> PostalAddress:
    """Return a Paris address that already carries its coordinate.

    Returns:
        PostalAddress: An address the geocoder never has to resolve.

    Notes:
        The coordinate is supplied so validation never reaches Nominatim. The
        suite's autouse ``suppress_geocoding`` fixture covers that too, but a
        fixture that also happens to be resolved is what lets the distance
        assertions mean something.
    """
    return PostalAddress(
        street="10 rue de la Roquette",
        postal_code="75011",
        city="Paris",
        latitude=48.8551,
        longitude=2.3720,
    )


class TestAgency:
    """Tests for the Agency model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(self) -> None:
        """A site needs only a company and a name."""
        agency = Agency(company_id="company-1", name="Siege")
        assert agency.company_id == "company-1"
        assert agency.name == "Siege"
        assert agency.id is None
        assert agency.address is None

    def test_the_default_type_is_a_branch_office(self) -> None:
        """A site created without a type is an ordinary branch.

        Notes:
            The head office is decided by the service counting the company's
            existing sites, so a payload that says nothing must get the safe
            answer rather than the privileged one.
        """
        assert Agency(company_id="c", name="n").agency_type is AgencyType.OFFICE

    def test_whitespace_is_trimmed(self) -> None:
        """Identifiers and the name are stored trimmed."""
        agency = Agency(id="  a-1 ", company_id=" c-1 ", name="  Siege  ")
        assert agency.id == "a-1"
        assert agency.company_id == "c-1"
        assert agency.name == "Siege"

    # ------------------------------------------------------------------ #
    #  id validation
    # ------------------------------------------------------------------ #

    def test_a_missing_id_is_accepted(self) -> None:
        """The identifier is absent until the store assigns one."""
        assert Agency(company_id="c", name="n").id is None

    @pytest.mark.parametrize(
        "invalid_id",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace only"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_id_is_refused(self, invalid_id: ModelInput) -> None:
        """A present identifier must be a non-empty string."""
        with pytest.raises(MTAgencyInvalidId):
            Agency(id=invalid_id, company_id="c", name="n")

    # ------------------------------------------------------------------ #
    #  company_id validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_company_id",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - whitespace only"),
            pytest.param(3, id="Invalid - not a string"),
        ],
    )
    def test_a_site_must_name_its_company(self, invalid_company_id: ModelInput) -> None:
        """A site belonging to no company is refused rather than stored."""
        with pytest.raises(MTAgencyInvalidCompanyId):
            Agency(company_id=invalid_company_id, name="n")

    # ------------------------------------------------------------------ #
    #  name validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace only"),
            pytest.param(1, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_name_is_refused(self, invalid_name: ModelInput) -> None:
        """The one field an operator sees cannot be blank."""
        with pytest.raises(MTAgencyInvalidName):
            Agency(company_id="c", name=invalid_name)

    def test_a_name_at_the_limit_is_accepted(self) -> None:
        """The length bound is inclusive."""
        name = "n" * Agency.MAX_NAME_LENGTH
        assert Agency(company_id="c", name=name).name == name

    def test_a_name_past_the_limit_is_refused(self) -> None:
        """One character over the bound is refused."""
        with pytest.raises(MTAgencyInvalidName):
            Agency(company_id="c", name="n" * (Agency.MAX_NAME_LENGTH + 1))

    # ------------------------------------------------------------------ #
    #  agency_type validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("value", list(AgencyType))
    def test_every_declared_type_is_accepted(self, value: AgencyType) -> None:
        """Each member of the enumeration is a usable type."""
        assert Agency(company_id="c", name="n", agency_type=value).agency_type is value

    def test_the_type_is_accepted_as_its_string(self) -> None:
        """A payload carries the value, not the member."""
        agency = Agency(company_id="c", name="n", agency_type="warehouse")
        assert agency.agency_type is AgencyType.WAREHOUSE

    def test_a_missing_type_reads_as_a_branch_office(self) -> None:
        """``None`` is the safe answer rather than an error."""
        agency = Agency(company_id="c", name="n", agency_type=None)
        assert agency.agency_type is AgencyType.OFFICE

    @pytest.mark.parametrize(
        "invalid_type",
        [
            pytest.param("head-office", id="Invalid - not a member"),
            pytest.param(2, id="Invalid - not a string"),
            pytest.param(["hq"], id="Invalid - a list"),
        ],
    )
    def test_an_unknown_type_is_refused(self, invalid_type: ModelInput) -> None:
        """A value the enumeration does not carry is refused."""
        with pytest.raises(MTAgencyInvalidType):
            Agency(company_id="c", name="n", agency_type=invalid_type)

    # ------------------------------------------------------------------ #
    #  address validation
    # ------------------------------------------------------------------ #

    def test_a_site_may_have_no_address(self) -> None:
        """A company founded through the public form supplies none.

        Notes:
            Refusing the state would block ``CompanyRegistrationService``, which
            creates a company from a form that asks for no address at all.
        """
        assert Agency(company_id="c", name="n", address=None).address is None

    def test_an_address_is_accepted_as_a_mapping(self) -> None:
        """A request body carries the address as JSON."""
        agency = Agency(
            company_id="c",
            name="n",
            address={
                "street": "10 rue de la Roquette",
                "postal_code": "75011",
                "city": "Paris",
                "latitude": 48.8551,
                "longitude": 2.3720,
            },
        )
        assert agency.address is not None
        assert agency.address.city == "Paris"

    @pytest.mark.parametrize(
        "invalid_address",
        [
            pytest.param("10 rue de la Roquette", id="Invalid - a bare string"),
            pytest.param(42, id="Invalid - a number"),
            pytest.param(["street"], id="Invalid - a list"),
        ],
    )
    def test_something_that_is_not_an_address_is_refused(
        self, invalid_address: ModelInput
    ) -> None:
        """A value that is not an address at all raises this model's own error.

        Notes:
            Without the check it would surface as a raw Pydantic error, which
            the API's exception-to-status map has no row for and would answer
            as a 500.
        """
        with pytest.raises(MTAgencyInvalidAddress):
            Agency(company_id="c", name="n", address=invalid_address)

    # ------------------------------------------------------------------ #
    #  timestamp validation
    # ------------------------------------------------------------------ #

    def test_timestamps_are_parsed_from_iso_strings(self) -> None:
        """A store hands them back as text."""
        agency = Agency(
            company_id="c",
            name="n",
            created_at="2026-08-12T09:00:00+00:00",
            updated_at=datetime(2026, 8, 12, 10, tzinfo=timezone.utc),
        )
        assert agency.created_at == datetime(2026, 8, 12, 9, tzinfo=timezone.utc)
        assert agency.updated_at == datetime(2026, 8, 12, 10, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "invalid_timestamp",
        [
            pytest.param("not a date", id="Invalid - unparseable"),
            pytest.param(17, id="Invalid - a number"),
        ],
    )
    def test_a_malformed_timestamp_is_refused(
        self, invalid_timestamp: ModelInput
    ) -> None:
        """Anything that is not a datetime is refused."""
        with pytest.raises(MTAgencyInvalidDate):
            Agency(company_id="c", name="n", created_at=invalid_timestamp)

    def test_timestamps_serialise_as_iso_strings(self) -> None:
        """The wire form is ISO-8601."""
        agency = Agency(
            company_id="c",
            name="n",
            created_at=datetime(2026, 8, 12, 9, tzinfo=timezone.utc),
        )
        assert agency.model_dump()["created_at"] == "2026-08-12T09:00:00+00:00"
        assert agency.model_dump()["updated_at"] is None

    # ------------------------------------------------------------------ #
    #  Behaviour
    # ------------------------------------------------------------------ #

    def test_only_the_head_office_is_the_head_office(self) -> None:
        """The predicate follows the type."""
        assert Agency(company_id="c", name="n", agency_type="hq").is_headquarters()
        assert not Agency(company_id="c", name="n").is_headquarters()

    def test_the_coordinate_comes_from_the_address(self) -> None:
        """A resolved address yields the point the distance rule uses."""
        point = Agency(company_id="c", name="n", address=_address()).coordinate()
        assert point is not None
        assert point.latitude == pytest.approx(48.8551)
        assert point.longitude == pytest.approx(2.3720)

    def test_a_site_with_no_address_has_no_coordinate(self) -> None:
        """``None`` is a real answer, not an error."""
        assert Agency(company_id="c", name="n").coordinate() is None

    # ------------------------------------------------------------------ #
    #  The company's own attributes
    # ------------------------------------------------------------------ #

    def test_a_site_carries_every_company_attribute(self) -> None:
        """**A site extends the company rather than merely referring to one.**

        Notes:
            The head office is where the business is registered, and the quote
            and invoice renderers print the SIRET, the VAT number and the bank
            details from the site the document was written at. Declaring those
            fields again on ``Agency`` would be a second copy free to disagree
            with the first.
        """
        for field in Company.model_fields:
            assert field in Agency.model_fields, field

    def test_the_head_office_holds_the_legal_identity(self) -> None:
        """A head office may carry the business's identity, and reads it back."""
        agency = Agency(
            company_id="c",
            name="Siege",
            agency_type="hq",
            registration_number="123 456 789",
            vat_number="FR 12345678901",
            iban="FR76 3000 6000 0112 3456 7890 189",
            legal_form="SAS",
        )
        assert agency.holds_legal_identity()
        assert agency.siren() == "123456789"
        assert agency.vat_number == "FR12345678901"
        assert agency.masked_iban() is not None

    @pytest.mark.parametrize(
        "branch_type",
        [
            pytest.param("office", id="branch office"),
            pytest.param("warehouse", id="warehouse"),
        ],
    )
    @pytest.mark.parametrize(
        "field",
        list(Agency.LEGAL_IDENTITY_FIELDS),
    )
    def test_a_branch_may_not_carry_the_legal_identity(
        self, branch_type: str, field: str
    ) -> None:
        """**One legal entity, one place it is registered.**

        Args:
            branch_type (str): The kind of site being built.
            field (str): The legal-identity field being smuggled onto it.

        Notes:
            A warehouse carrying its own SIRET and its own IBAN would print two
            different companies on two quotes from one agency, and route two
            different bank accounts on two invoices.
        """
        values = {
            "registration_number": "123456789",
            "legal_form": "SARL",
            "share_capital": "10000",
            "rcs_number": "RCS Paris B 123 456 789",
            "vat_number": "FR12345678901",
            "sap_declaration_number": "SAP123",
            "iban": "FR7630006000011234567890189",
            "bic": "BNPAFRPP",
        }
        with pytest.raises(MTAgencyLegalIdentityMisplaced):
            Agency(
                company_id="c",
                name="Antenne",
                agency_type=branch_type,
                **{field: values[field]},
            )

    def test_a_branch_keeps_its_own_place_details(self) -> None:
        """A telephone number and an address belong to the building.

        Notes:
            Deliberately outside :attr:`Agency.LEGAL_IDENTITY_FIELDS`. A branch
            has its own switchboard and its own street, and refusing those would
            make every site print the head office's contact details.
        """
        agency = Agency(
            company_id="c",
            name="Antenne Est",
            agency_type="office",
            phone_number="01 23 45 67 89",
            contact_email="Est@Example.FR",
            address=_address(),
        )
        assert agency.phone_number == "01 23 45 67 89"
        assert agency.contact_email == "est@example.fr"
        assert not agency.holds_legal_identity()

    def test_an_unresolved_address_has_no_coordinate(self) -> None:
        """An address the geocoder could not place is not a point at zero.

        Notes:
            Reading an unresolved address as ``(0, 0)`` would put the site off
            the coast of Africa and make it the closest one to nobody — or, with
            two such sites, the closest one to everybody.
        """
        unresolved = PostalAddress(
            street="1 rue Introuvable",
            postal_code="99999",
            city="Nulle Part",
            geocoding_error="not_found",
        )
        assert Agency(company_id="c", name="n", address=unresolved).coordinate() is None
