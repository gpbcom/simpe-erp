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
    MTAgencyViewInvalidCount,
    MTAgencyViewInvalidName,
    MTInvalidAgencyViewException,
    MTInvalidTeamDocumentConstraintsResponseException,
    MTInvalidTeamViewException,
    MTTeamDocumentConstraintsResponseInvalidContentTypes,
    MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes,
    MTTeamViewInvalidCount,
    MTTeamViewInvalidName,
)
from models.schemas.responses.organisation.agency_view import AgencyView
from models.schemas.responses.organisation.team_document_constraints_response import (
    TeamDocumentConstraintsResponse,
)
from models.schemas.responses.organisation.team_view import TeamView
from tests.annotations import ModelInput


class TestAgencyView:
    """Tests for the AgencyView schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_projects_a_site_and_its_counts(self) -> None:
        """The grid's row: what the site is, and how much hangs off it."""
        view = AgencyView.from_agency(
            Agency(
                id="agency-1",
                company_id="company-1",
                name="Siège",
                agency_type=AgencyType.HQ,
                address=PostalAddress(
                    street="1 rue A", city="Paris", postal_code="75001"
                ),
            ),
            member_count=4,
            team_count=2,
        )
        assert view.id == "agency-1"
        assert view.member_count == 4
        assert view.team_count == 2
        assert view.address is not None

    def test_being_the_head_office_travels_as_a_flag(self) -> None:
        """A client never has to compare against the literal ``"hq"``."""
        head = AgencyView.from_agency(
            Agency(company_id="company-1", name="Siège", agency_type=AgencyType.HQ)
        )
        branch = AgencyView.from_agency(
            Agency(
                company_id="company-1", name="Antenne", agency_type=AgencyType.OFFICE
            )
        )
        assert head.is_headquarters is True
        assert branch.is_headquarters is False

    def test_a_new_site_is_projected_with_no_counts(self) -> None:
        """A site created a moment ago has neither members nor teams."""
        view = AgencyView.from_agency(Agency(company_id="company-1", name="Antenne"))
        assert view.member_count == 0
        assert view.team_count == 0

    def test_it_declares_no_legal_identity(self) -> None:
        """The one protection this projection exists for.

        Notes:
            A site *is* a company, so the record behind it carries the SIRET and
            the account invoices are paid into. This asserts on the field set
            rather than on a value, because the risk is a field being *added*
            later rather than one being populated today.
        """
        declared = set(AgencyView.model_fields)
        assert declared.isdisjoint(set(Agency.LEGAL_IDENTITY_FIELDS))
        assert "logo_url" not in declared

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    def test_an_invalid_name_raises(self) -> None:
        """A projected site with no name is an unlabelled row."""
        with pytest.raises(MTAgencyViewInvalidName):
            AgencyView(company_id="company-1", name="", agency_type=AgencyType.OFFICE)

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param("4", id="Invalid - string"),
        ],
    )
    def test_an_invalid_count_raises(self, invalid_value: ModelInput) -> None:
        """A count that is not a count would read as a fact on screen."""
        with pytest.raises(MTAgencyViewInvalidCount):
            AgencyView(
                company_id="company-1",
                name="Antenne",
                agency_type=AgencyType.OFFICE,
                member_count=invalid_value,
            )

    def test_an_absent_count_is_zero(self) -> None:
        """A grouped count has no row for a site nothing is attached to."""
        view = AgencyView(
            company_id="company-1",
            name="Antenne",
            agency_type=AgencyType.OFFICE,
            member_count=None,
        )
        assert view.member_count == 0

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [MTAgencyViewInvalidCount, MTAgencyViewInvalidName],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the projection's own family."""
        assert issubclass(exception_class, MTInvalidAgencyViewException)


class TestTeamView:
    """Tests for the TeamView schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_projects_a_team_and_its_size(self) -> None:
        """The grid's row: which team, at which site, under whom, how many."""
        view = TeamView.from_team(
            Team(
                id="team-1",
                company_id="company-1",
                agency_id="agency-1",
                name="Équipe Est",
                manager_user_id="user-1",
            ),
            member_count=5,
        )
        assert view.id == "team-1"
        assert view.agency_id == "agency-1"
        assert view.manager_user_id == "user-1"
        assert view.member_count == 5

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    def test_an_invalid_name_raises(self) -> None:
        """A projected team with no name is an unlabelled row."""
        with pytest.raises(MTTeamViewInvalidName):
            TeamView(
                company_id="company-1",
                agency_id="agency-1",
                name="   ",
                manager_user_id="user-1",
            )

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(True, id="Invalid - bool"),
        ],
    )
    def test_an_invalid_count_raises(self, invalid_value: ModelInput) -> None:
        """A member count that is not a count would read as a fact."""
        with pytest.raises(MTTeamViewInvalidCount):
            TeamView(
                company_id="company-1",
                agency_id="agency-1",
                name="Équipe Est",
                manager_user_id="user-1",
                member_count=invalid_value,
            )

    def test_zero_is_accepted(self) -> None:
        """A stored team always has its manager; a race must not fail a page."""
        view = TeamView(
            company_id="company-1",
            agency_id="agency-1",
            name="Équipe Est",
            manager_user_id="user-1",
            member_count=0,
        )
        assert view.member_count == 0

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [MTTeamViewInvalidCount, MTTeamViewInvalidName],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the projection's own family."""
        assert issubclass(exception_class, MTInvalidTeamViewException)


class TestTeamDocumentConstraintsResponse:
    """Tests for the TeamDocumentConstraintsResponse schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_publishes_the_limit_and_the_types(self) -> None:
        """A client refuses an unshareable file before it uploads it."""
        response = TeamDocumentConstraintsResponse(
            max_upload_bytes=5_242_880,
            accepted_content_types=["application/pdf", "image/png"],
        )
        assert response.max_upload_bytes == 5_242_880
        assert response.accepted_content_types == ["application/pdf", "image/png"]

    def test_media_types_are_normalised(self) -> None:
        """A type is published in the form a client compares against."""
        response = TeamDocumentConstraintsResponse(
            max_upload_bytes=1,
            accepted_content_types=(" Application/PDF ", "IMAGE/PNG"),
        )
        assert response.accepted_content_types == ["application/pdf", "image/png"]

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(0, id="Invalid - zero"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param(True, id="Invalid - bool"),
            pytest.param(None, id="Invalid - None"),
        ],
    )
    def test_an_invalid_limit_raises(self, invalid_value: ModelInput) -> None:
        """A limit that is not a positive integer refuses every document."""
        with pytest.raises(MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes):
            TeamDocumentConstraintsResponse(
                max_upload_bytes=invalid_value,
                accepted_content_types=["application/pdf"],
            )

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param([], id="Invalid - empty"),
            pytest.param("application/pdf", id="Invalid - bare string"),
            pytest.param(None, id="Invalid - None"),
            pytest.param([""], id="Invalid - empty entry"),
        ],
    )
    def test_invalid_media_types_raise(self, invalid_value: ModelInput) -> None:
        """Publishing no type would say nothing may ever be shared."""
        with pytest.raises(MTTeamDocumentConstraintsResponseInvalidContentTypes):
            TeamDocumentConstraintsResponse(
                max_upload_bytes=1, accepted_content_types=invalid_value
            )

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTTeamDocumentConstraintsResponseInvalidContentTypes,
            MTTeamDocumentConstraintsResponseInvalidMaxUploadBytes,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the response's own family."""
        assert issubclass(
            exception_class, MTInvalidTeamDocumentConstraintsResponseException
        )
