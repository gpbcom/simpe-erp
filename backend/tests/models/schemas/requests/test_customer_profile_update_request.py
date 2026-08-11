from __future__ import annotations

# Standard library imports
from typing import Any, Dict

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTCustomerProfileUpdateRequestInvalidName,
    MTInvalidCustomerProfileUpdateRequestException,
)
from models.schemas.requests.customers.customer_profile_update_request import (
    CustomerProfileUpdateRequest,
)


def _payload(**overrides: Any) -> Dict[str, Any]:
    """Build a valid payload, with overrides applied.

    Args:
        **overrides (Any): Fields to replace.

    Returns:
        Dict[str, Any]: The constructor keyword arguments.
    """
    return {
        "first_name": "Marie",
        "last_name": "Durand",
        "phone_number": "+33612345678",
        "email": "marie.durand@example.com",
        "address": {
            "street": "12 rue de Rivoli",
            "postal_code": "75004",
            "city": "Paris",
            "latitude": 48.8558,
            "longitude": 2.3588,
        },
        **overrides,
    }


class TestCustomerProfileUpdateRequest:
    """Tests for what a household may change about themselves."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_the_contact_block_is_accepted(self) -> None:
        """The ordinary case works."""
        payload = CustomerProfileUpdateRequest(**_payload())

        assert payload.first_name == "Marie"
        assert payload.address.city == "Paris"

    # ------------------------------------------------------------------ #
    #  The shape is the permission
    # ------------------------------------------------------------------ #

    def test_it_carries_only_the_contact_fields(self) -> None:
        """**This test is the rule.**

        Notes:
            Two fields are deliberately absent and each would be a hole:

            - ``registration_status`` — a household that could set their own
              status would promote themselves from ``prospect`` to ``active``,
              and being active is exactly what makes the planner schedule their
              work. That is the gate ``can_be_scheduled`` exists for, handed to
              the party it gates.
            - ``billing_periodicity`` — how often somebody is invoiced is a
              commercial term the agency agrees, not a preference.

            A field added here silently widens what a household may do, which is
            why the assertion is on the whole set.
        """
        assert set(CustomerProfileUpdateRequest.model_fields) == {
            "first_name",
            "last_name",
            "phone_number",
            "email",
            "address",
        }

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            pytest.param("registration_status", "active", id="self-promotion"),
            pytest.param("billing_periodicity", "yearly", id="own billing terms"),
            pytest.param("id", "customer-99", id="somebody else's file"),
        ],
    )
    def test_an_unwanted_field_does_not_ride_along(
        self, field: str, value: str
    ) -> None:
        """A value the model has no field for never reaches the customer.

        Args:
            field (str): The field that must not be honoured.
            value (str): What a household might try to send.

        Notes:
            The self-promotion case is the one that matters. Honoured, a
            prospect could make themselves active and put their own work into
            the next planning run — the agency would be delivering care it never
            agreed to.
        """
        payload = CustomerProfileUpdateRequest(**_payload(**{field: value}))

        assert not hasattr(payload, field)

    # ------------------------------------------------------------------ #
    #  name validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", ["first_name", "last_name"])
    def test_a_name_is_trimmed(self, field: str) -> None:
        """Surrounding space is the typist's.

        Args:
            field (str): The name part under test.
        """
        payload = CustomerProfileUpdateRequest(**_payload(**{field: "  Marie  "}))

        assert getattr(payload, field) == "Marie"

    @pytest.mark.parametrize("field", ["first_name", "last_name"])
    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace"),
            pytest.param(None, id="Invalid - missing"),
            pytest.param(42, id="Invalid - int"),
        ],
    )
    def test_a_missing_name_is_refused(self, field: str, value: Any) -> None:
        """Both parts are required, unlike on an account.

        Args:
            field (str): The name part under test.
            value (Any): The rejected value.

        Notes:
            An account may be a mononym or a service account and leave the given
            name blank. This is a household on a printed invoice and on an
            assistant's round sheet, and half a name on either is a call to the
            office.
        """
        with pytest.raises(MTCustomerProfileUpdateRequestInvalidName):
            CustomerProfileUpdateRequest(**_payload(**{field: value}))

    # ------------------------------------------------------------------ #
    #  Required fields
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "field", ["first_name", "last_name", "phone_number", "email", "address"]
    )
    def test_every_field_is_required(self, field: str) -> None:
        """The block is replaced wholesale, so nothing may be omitted.

        Args:
            field (str): The field to leave out.

        Notes:
            A partial payload would read as a household clearing what it omits —
            which is how somebody becomes unreachable when an assistant is
            running late.
        """
        incomplete = _payload()
        del incomplete[field]

        with pytest.raises(
            (ValidationError, MTCustomerProfileUpdateRequestInvalidName)
        ):
            CustomerProfileUpdateRequest(**incomplete)

    def test_a_malformed_telephone_number_is_refused(self) -> None:
        """The number is how the agency reaches them on the day."""
        with pytest.raises(ValidationError):
            CustomerProfileUpdateRequest(**_payload(phone_number="not-a-number"))

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    def test_the_exception_belongs_to_the_registered_family(self) -> None:
        """The leaf inherits the family the API maps to 422."""
        assert issubclass(
            MTCustomerProfileUpdateRequestInvalidName,
            MTInvalidCustomerProfileUpdateRequestException,
        )
