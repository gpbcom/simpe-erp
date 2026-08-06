from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
import pytest

# First-party imports
from models.schemas.exceptions import MTInterventionTypeChangeRequestInvalidTypeId
from models.schemas.requests.intervention_type_change_request import (
    InterventionTypeChangeRequest,
)


class TestInterventionTypeChangeRequest:
    """Tests for what may be sent when re-classifying a scheduled visit."""

    def test_a_type_identifier_is_enough(self) -> None:
        """One field, because one thing is being decided."""
        request = InterventionTypeChangeRequest(intervention_type_id="type-comfort")

        assert request.intervention_type_id == "type-comfort"

    def test_an_identifier_is_stripped(self) -> None:
        """Surrounding space is not part of an identifier."""
        request = InterventionTypeChangeRequest(intervention_type_id="  type-1  ")

        assert request.intervention_type_id == "type-1"

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_a_missing_or_blank_identifier_is_refused(
        self, value: Union[str, None, int]
    ) -> None:
        """There is no default, and that is the point.

        Args:
            value (Union[str, None, int]): The rejected identifier.

        Notes:
            An empty body that silently meant "leave it alone" would answer 200
            to a request that changed nothing, and the manager would go on
            believing the quote had been repriced.
        """
        with pytest.raises(MTInterventionTypeChangeRequestInvalidTypeId):
            InterventionTypeChangeRequest(intervention_type_id=value)

    def test_the_refusal_is_the_model_s_own_exception(self) -> None:
        """Never a built-in, so the API boundary can answer it as a 422."""
        with pytest.raises(MTInterventionTypeChangeRequestInvalidTypeId):
            InterventionTypeChangeRequest.validate_intervention_type_id("")

    def test_no_amount_can_ride_along(self) -> None:
        """What the visit now costs is the server's answer, not the caller's.

        Notes:
            Pydantic ignores unknown fields rather than refusing them, so this
            asserts on what the model *carries*: a price sent from a screen
            cannot reach the pricing code, because there is nowhere for it to
            land.
        """
        assert set(InterventionTypeChangeRequest.model_fields) == {
            "intervention_type_id"
        }
