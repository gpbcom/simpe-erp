from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTAccountUpdateRequestInvalidEmail,
    MTAccountUpdateRequestInvalidFullName,
)
from models.schemas.requests.account_update_request import AccountUpdateRequest


class TestAccountUpdateRequest:
    """Tests for the payload an account holder may send about themselves."""

    def test_a_complete_payload_is_accepted(self) -> None:
        """The ordinary case."""
        request = AccountUpdateRequest(
            full_name="Luc Martin", email="luc.martin@simple-erp.fr"
        )

        assert request.full_name == "Luc Martin"
        assert request.email == "luc.martin@simple-erp.fr"

    def test_a_name_is_stripped(self) -> None:
        """Surrounding space is not part of a name."""
        request = AccountUpdateRequest(
            full_name="  Luc Martin  ", email="luc@simple-erp.fr"
        )

        assert request.full_name == "Luc Martin"

    def test_an_address_is_lower_cased(self) -> None:
        """**The case that would lock somebody out.**

        Notes:
            Accounts are looked up by exact address. Saving ``Luc.Martin@``
            from the account screen would leave the holder unable to sign in
            with the address they used yesterday, and the sign-in form gives
            the same message for a wrong password as for an unknown address —
            so nothing would tell them what had happened.
        """
        request = AccountUpdateRequest(
            full_name="Luc", email="Luc.Martin@SIMPLE-ERP.FR"
        )

        assert request.email == "luc.martin@simple-erp.fr"

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_a_missing_or_blank_name_is_refused(self, value: Union[str, None]) -> None:
        """A name of spaces is not a name.

        Args:
            value (Union[str, None]): The rejected ``full_name``.
        """
        with pytest.raises(MTAccountUpdateRequestInvalidFullName):
            AccountUpdateRequest(full_name=value, email="luc@simple-erp.fr")

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_a_missing_or_blank_address_is_refused(
        self, value: Union[str, None]
    ) -> None:
        """An account with no sign-in address could not sign in.

        Args:
            value (Union[str, None]): The rejected ``email``.
        """
        with pytest.raises(MTAccountUpdateRequestInvalidEmail):
            AccountUpdateRequest(full_name="Luc", email=value)

    @pytest.mark.parametrize(
        "value",
        ["not-an-address", "luc@", "@simple-erp.fr", "luc martin@simple-erp.fr"],
    )
    def test_a_malformed_address_is_refused(self, value: str) -> None:
        """Refused by the address parser, after the blank check.

        Args:
            value (str): The malformed address.
        """
        with pytest.raises(ValidationError):
            AccountUpdateRequest(full_name="Luc", email=value)

    def test_both_fields_are_required(self) -> None:
        """A partial payload cannot say what it means.

        Notes:
            With optional fields, "clear my display name" and "leave my display
            name alone" would arrive identically. The screen holds both values,
            so it can always send both.

            Reported as a plain ``ValidationError`` rather than as one of this
            model's own exceptions: a ``mode="before"`` validator does not run
            for a field that is absent, so "missing" is Pydantic's finding and
            "blank" is ours. Both reach the caller as a 422.
        """
        with pytest.raises(ValidationError):
            AccountUpdateRequest(full_name="Luc")
        with pytest.raises(ValidationError):
            AccountUpdateRequest(email="luc@simple-erp.fr")

    @pytest.mark.parametrize(
        "field,value",
        [
            ("role", "admin"),
            ("is_active", False),
            ("hca_id", "hca-9"),
            ("company_id", "company-9"),
            ("must_change_password", False),
            ("hashed_password", "$2b$12$smuggled"),
            ("id", "user-9"),
        ],
    )
    def test_a_privileged_field_cannot_be_carried(
        self, field: str, value: object
    ) -> None:
        """**The permission, asserted as the shape of the model.**

        Args:
            field (str): The field somebody might try to smuggle in.
            value (object): What they would set it to.

        Notes:
            None of these exist on the model, so a payload carrying one parses
            without it — there is no attribute to read afterwards. Enumerated
            rather than assumed: adding a field here later would silently make
            it self-settable, and this is the test that would go red.
        """
        request = AccountUpdateRequest(
            **{"full_name": "Luc", "email": "luc@simple-erp.fr", field: value}
        )

        assert not hasattr(request, field)

    def test_only_two_fields_are_serialised(self) -> None:
        """What the service is handed is a name and an address, and nothing else."""
        request = AccountUpdateRequest(full_name="Luc", email="luc@simple-erp.fr")

        assert set(request.model_dump()) == {"full_name", "email"}
