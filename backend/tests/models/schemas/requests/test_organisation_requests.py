from __future__ import annotations

# Standard library imports

# Third-party imports
import pytest

# First-party imports
from models.enums import AgencyType
from models.geo.postal_address import PostalAddress
from models.organisation.agency.agency import Agency
from models.organisation.team.team import Team
from models.schemas.exceptions import (
    MTAgencyCreateRequestInvalidName,
    MTAgencyCreateRequestInvalidType,
    MTAgencyUpdateRequestInvalidName,
    MTAgencyUpdateRequestInvalidType,
    MTInvalidAgencyCreateRequestException,
    MTInvalidAgencyUpdateRequestException,
    MTInvalidTeamCreateRequestException,
    MTInvalidTeamUpdateRequestException,
    MTTeamCreateRequestInvalidAgencyId,
    MTTeamCreateRequestInvalidManagerUserId,
    MTTeamCreateRequestInvalidName,
    MTTeamUpdateRequestInvalidAgencyId,
    MTTeamUpdateRequestInvalidManagerUserId,
    MTTeamUpdateRequestInvalidName,
)
from models.schemas.requests.organisation.agency_create_request import (
    AgencyCreateRequest,
)
from models.schemas.requests.organisation.agency_update_request import (
    AgencyUpdateRequest,
)
from models.schemas.requests.organisation.team_create_request import (
    TeamCreateRequest,
)
from models.schemas.requests.organisation.team_update_request import (
    TeamUpdateRequest,
)
from tests.annotations import ModelInput


class TestAgencyCreateRequest:
    """Tests for the AgencyCreateRequest schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_describes_a_branch_by_default(self) -> None:
        """A payload that says nothing about the type asks for a branch."""
        request = AgencyCreateRequest(name="Antenne Est")
        assert request.agency_type is AgencyType.OFFICE
        assert request.address is None

    def test_the_name_is_trimmed(self) -> None:
        """Surrounding whitespace never reaches the stored name."""
        assert AgencyCreateRequest(name="  Antenne Est  ").name == "Antenne Est"

    def test_the_type_is_read_from_its_value(self) -> None:
        """A client sends the enum's wire value, not its member name."""
        request = AgencyCreateRequest(name="Siège", agency_type="HQ")
        assert request.agency_type is AgencyType.HQ

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(42, id="Invalid - not a string"),
        ],
    )
    def test_an_invalid_name_raises(self, invalid_value: ModelInput) -> None:
        """A site nobody can name is an unlabelled row in a picker."""
        with pytest.raises(MTAgencyCreateRequestInvalidName):
            AgencyCreateRequest(name=invalid_value)

    def test_a_name_beyond_the_limit_raises(self) -> None:
        """The payload refuses what the record it becomes could not hold."""
        with pytest.raises(MTAgencyCreateRequestInvalidName):
            AgencyCreateRequest(name="e" * (Agency.MAX_NAME_LENGTH + 1))

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("depot", id="Invalid - unknown type"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_an_invalid_type_raises(self, invalid_value: ModelInput) -> None:
        """A type nothing recognises would be a grey chip on every screen."""
        with pytest.raises(MTAgencyCreateRequestInvalidType):
            AgencyCreateRequest(name="Antenne Est", agency_type=invalid_value)

    # ------------------------------------------------------------------ #
    #  Conversion
    # ------------------------------------------------------------------ #

    def test_it_builds_a_site_owned_by_the_caller(self) -> None:
        """The company comes from the credential, never from the body."""
        agency = AgencyCreateRequest(
            name="Antenne Est",
            address=PostalAddress(street="1 rue A", city="Lyon", postal_code="69001"),
        ).to_agency("company-1")
        assert agency.company_id == "company-1"
        assert agency.id is None
        assert agency.address is not None
        assert agency.address.city == "Lyon"

    def test_it_carries_no_legal_identity(self) -> None:
        """No payload can set the SIRET or the account invoices are paid into."""
        agency = AgencyCreateRequest(name="Antenne Est").to_agency("company-1")
        assert all(
            getattr(agency, field) is None for field in Agency.LEGAL_IDENTITY_FIELDS
        )

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTAgencyCreateRequestInvalidName,
            MTAgencyCreateRequestInvalidType,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the payload's own family."""
        assert issubclass(exception_class, MTInvalidAgencyCreateRequestException)


class TestAgencyUpdateRequest:
    """Tests for the AgencyUpdateRequest schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_accepts_the_three_site_fields(self) -> None:
        """Name, address and type; nothing about the business behind them."""
        request = AgencyUpdateRequest(name="Antenne Est", agency_type="warehouse")
        assert request.agency_type is AgencyType.WAREHOUSE

    def test_an_absent_address_means_the_site_has_none(self) -> None:
        """Clearing an address is a thing an administrator legitimately means."""
        assert AgencyUpdateRequest(name="Antenne Est").address is None

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_invalid_name_raises(self, invalid_value: ModelInput) -> None:
        """A rename to nothing is refused before it reaches the store."""
        with pytest.raises(MTAgencyUpdateRequestInvalidName):
            AgencyUpdateRequest(name=invalid_value)

    def test_an_invalid_type_raises(self) -> None:
        """Only the kinds of site the enum knows may be asked for."""
        with pytest.raises(MTAgencyUpdateRequestInvalidType):
            AgencyUpdateRequest(name="Antenne Est", agency_type="depot")

    # ------------------------------------------------------------------ #
    #  Conversion
    # ------------------------------------------------------------------ #

    def test_the_identifier_comes_from_the_route(self) -> None:
        """Neither the site nor the company can be moved by the body."""
        agency = AgencyUpdateRequest(name="Antenne Est").to_agency(
            "agency-1", "company-1"
        )
        assert agency.id == "agency-1"
        assert agency.company_id == "company-1"

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTAgencyUpdateRequestInvalidName,
            MTAgencyUpdateRequestInvalidType,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the payload's own family."""
        assert issubclass(exception_class, MTInvalidAgencyUpdateRequestException)


class TestTeamCreateRequest:
    """Tests for the TeamCreateRequest schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_names_a_site_and_a_manager(self) -> None:
        """A team without either could never be planned."""
        request = TeamCreateRequest(
            name="  Équipe Est  ", agency_id=" agency-1 ", manager_user_id=" user-1 "
        )
        assert request.name == "Équipe Est"
        assert request.agency_id == "agency-1"
        assert request.manager_user_id == "user-1"

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_invalid_name_raises(self, invalid_value: ModelInput) -> None:
        """A team nobody can name is a row nobody can pick."""
        with pytest.raises(MTTeamCreateRequestInvalidName):
            TeamCreateRequest(
                name=invalid_value, agency_id="agency-1", manager_user_id="user-1"
            )

    def test_a_name_beyond_the_limit_raises(self) -> None:
        """The payload refuses what the record it becomes could not hold."""
        with pytest.raises(MTTeamCreateRequestInvalidName):
            TeamCreateRequest(
                name="e" * (Team.MAX_NAME_LENGTH + 1),
                agency_id="agency-1",
                manager_user_id="user-1",
            )

    def test_a_missing_site_raises(self) -> None:
        """A team with no site can never be the closest one to a customer."""
        with pytest.raises(MTTeamCreateRequestInvalidAgencyId):
            TeamCreateRequest(name="Équipe Est", agency_id="", manager_user_id="user-1")

    def test_a_missing_manager_raises(self) -> None:
        """Exactly one manager is a cardinality the payload cannot dodge."""
        with pytest.raises(MTTeamCreateRequestInvalidManagerUserId):
            TeamCreateRequest(
                name="Équipe Est", agency_id="agency-1", manager_user_id=None
            )

    # ------------------------------------------------------------------ #
    #  Conversion
    # ------------------------------------------------------------------ #

    def test_it_builds_a_team_owned_by_the_caller(self) -> None:
        """The company comes from the credential, never from the body."""
        team = TeamCreateRequest(
            name="Équipe Est", agency_id="agency-1", manager_user_id="user-1"
        ).to_team("company-1")
        assert team.company_id == "company-1"
        assert team.id is None

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTTeamCreateRequestInvalidAgencyId,
            MTTeamCreateRequestInvalidManagerUserId,
            MTTeamCreateRequestInvalidName,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the payload's own family."""
        assert issubclass(exception_class, MTInvalidTeamCreateRequestException)


class TestTeamUpdateRequest:
    """Tests for the TeamUpdateRequest schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_a_team_may_move_to_another_site(self) -> None:
        """A branch that relocates is an ordinary event, not a refusal."""
        request = TeamUpdateRequest(
            name="Équipe Est", agency_id="agency-2", manager_user_id="user-1"
        )
        assert request.agency_id == "agency-2"

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_invalid_name_raises(self, invalid_value: ModelInput) -> None:
        """A rename to nothing is refused before it reaches the store."""
        with pytest.raises(MTTeamUpdateRequestInvalidName):
            TeamUpdateRequest(
                name=invalid_value, agency_id="agency-1", manager_user_id="user-1"
            )

    def test_a_missing_site_raises(self) -> None:
        """An update cannot leave a team with nowhere to work from."""
        with pytest.raises(MTTeamUpdateRequestInvalidAgencyId):
            TeamUpdateRequest(
                name="Équipe Est", agency_id=None, manager_user_id="user-1"
            )

    def test_a_missing_manager_raises(self) -> None:
        """A team with no manager is one whose planning nobody may re-run."""
        with pytest.raises(MTTeamUpdateRequestInvalidManagerUserId):
            TeamUpdateRequest(
                name="Équipe Est", agency_id="agency-1", manager_user_id=""
            )

    # ------------------------------------------------------------------ #
    #  Conversion
    # ------------------------------------------------------------------ #

    def test_the_identifier_comes_from_the_route(self) -> None:
        """Neither the team nor the company can be moved by the body."""
        team = TeamUpdateRequest(
            name="Équipe Est", agency_id="agency-1", manager_user_id="user-1"
        ).to_team("team-1", "company-1")
        assert team.id == "team-1"
        assert team.company_id == "company-1"

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTTeamUpdateRequestInvalidAgencyId,
            MTTeamUpdateRequestInvalidManagerUserId,
            MTTeamUpdateRequestInvalidName,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the payload's own family."""
        assert issubclass(exception_class, MTInvalidTeamUpdateRequestException)
