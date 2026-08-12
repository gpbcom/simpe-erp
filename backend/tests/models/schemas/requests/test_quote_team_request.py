from __future__ import annotations

# Standard library imports

# Third-party imports
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTInvalidQuoteTeamRequestException,
    MTQuoteTeamRequestInvalidTeamId,
)
from models.schemas.requests.quoting.quote_team_request import QuoteTeamRequest
from tests.annotations import ModelInput


class TestQuoteTeamRequest:
    """Tests for the QuoteTeamRequest schema."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_it_names_the_destination_team(self) -> None:
        """One field, and it is the whole payload."""
        assert QuoteTeamRequest(team_id="team-2").team_id == "team-2"

    def test_the_identifier_is_trimmed(self) -> None:
        """Whitespace never reaches the stored column."""
        assert QuoteTeamRequest(team_id="  team-2  ").team_id == "team-2"

    # ------------------------------------------------------------------ #
    #  Field validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(None, id="Invalid - None"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_an_invalid_team_raises(self, invalid_value: ModelInput) -> None:
        """There is no "no team" value, and there must not be.

        Notes:
            A quote with no team is read by no planning run, so clearing the
            field would make the work vanish from every calendar while still
            looking accepted on the quote screen.
        """
        with pytest.raises(MTQuoteTeamRequestInvalidTeamId):
            QuoteTeamRequest(team_id=invalid_value)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    def test_the_exception_shares_its_base_class(self) -> None:
        """The per-field exception inherits from the payload's own family."""
        assert issubclass(
            MTQuoteTeamRequestInvalidTeamId, MTInvalidQuoteTeamRequestException
        )
