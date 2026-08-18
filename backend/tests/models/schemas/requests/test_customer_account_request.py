from __future__ import annotations

# Standard library imports

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTCustomerAccountRequestInvalidFullName,
    MTInvalidCustomerAccountRequestException,
)
from models.schemas.requests.customers.customer_account_request import (
    CustomerAccountRequest,
)
from tests.annotations import ModelInput


class TestCustomerAccountRequest:
    """Tests for the payload that gives a household access to their space."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_an_address_and_a_name_are_enough(self) -> None:
        """The ordinary case works."""
        payload = CustomerAccountRequest(
            email="marie.durand@example.com", full_name="Marie Durand"
        )

        assert payload.email == "marie.durand@example.com"
        assert payload.full_name == "Marie Durand"

    # ------------------------------------------------------------------ #
    #  The shape is the permission
    # ------------------------------------------------------------------ #

    def test_it_carries_only_an_address_and_a_name(self) -> None:
        """**This test is the rule.**

        Notes:
            Three fields are deliberately absent and each would be a hole:

            - ``customer_id`` — the household comes from the path. In the body
              too, a well-formed request would carry two answers to "whose
              account is this", and the invitation lands on the wrong file.
            - ``role`` — this route mints the one role that is *not* on the
              staff ladder. A role field would be a way to ask for an employee
              account through a customer-facing endpoint.
            - ``password`` — the temporary one is generated server-side, so the
              first credential is never one a manager typed into a ticket.

            A field added here silently widens what the route can do, which is
            why the assertion is on the whole set rather than on each absence.
        """
        assert set(CustomerAccountRequest.model_fields) == {"email", "full_name"}

    @pytest.mark.parametrize(
        "field",
        [
            pytest.param("customer_id", id="the household"),
            pytest.param("role", id="the role"),
            pytest.param("password", id="a chosen password"),
        ],
    )
    def test_an_unwanted_field_does_not_ride_along(self, field: str) -> None:
        """A value the model has no field for never reaches the service.

        Args:
            field (str): The field that must not be honoured.

        Notes:
            Pydantic ignores unknown fields by default, so this passes rather
            than raises — what matters is that the value cannot be read back
            off the model, and so can never reach the account that is created.
        """
        payload = CustomerAccountRequest(
            **{
                "email": "marie@example.com",
                "full_name": "Marie Durand",
                field: "admin",
            }
        )

        assert not hasattr(payload, field)

    # ------------------------------------------------------------------ #
    #  full_name validation
    # ------------------------------------------------------------------ #

    def test_the_name_is_trimmed(self) -> None:
        """Surrounding space is the typist's, not part of the name."""
        payload = CustomerAccountRequest(
            email="marie@example.com", full_name="  Marie Durand  "
        )

        assert payload.full_name == "Marie Durand"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace"),
            pytest.param(None, id="Invalid - missing"),
            pytest.param(42, id="Invalid - int"),
            pytest.param(["Marie"], id="Invalid - list"),
        ],
    )
    def test_a_missing_name_is_refused(self, value: ModelInput) -> None:
        """An account with no display name has nothing to greet anybody by.

        Args:
            value (ModelInput): The rejected value.
        """
        with pytest.raises(MTCustomerAccountRequestInvalidFullName):
            CustomerAccountRequest(email="marie@example.com", full_name=value)

    # ------------------------------------------------------------------ #
    #  email validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("marie", id="Invalid - no domain"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(None, id="Invalid - missing"),
        ],
    )
    def test_a_malformed_address_is_refused(self, value: ModelInput) -> None:
        """The address is the credential. It has to be reachable.

        Args:
            value (ModelInput): The rejected value.

        Notes:
            Pydantic's own ``ValidationError`` rather than a model exception,
            because ``EmailStr`` does the work. Both answer 422.
        """
        with pytest.raises(ValidationError):
            CustomerAccountRequest(email=value, full_name="Marie Durand")

    def test_there_is_no_default_address(self) -> None:
        """An empty body cannot create an account nobody can sign in to."""
        with pytest.raises(ValidationError):
            CustomerAccountRequest(full_name="Marie Durand")

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    def test_the_exception_belongs_to_the_registered_family(self) -> None:
        """The leaf inherits the family ``exception_handlers.py`` maps.

        Notes:
            A leaf outside it answers 500 instead of 422, which reads to the
            screen as the server being broken rather than the form being wrong.
        """
        assert issubclass(
            MTCustomerAccountRequestInvalidFullName,
            MTInvalidCustomerAccountRequestException,
        )

    # ------------------------------------------------------------------ #
    #  Serialization
    # ------------------------------------------------------------------ #

    def test_it_round_trips(self) -> None:
        """The payload survives a dump-and-rebuild unchanged."""
        payload = CustomerAccountRequest(
            email="marie@example.com", full_name="Marie Durand"
        )

        assert CustomerAccountRequest(**payload.model_dump()) == payload
