from __future__ import annotations

# Standard library imports
from typing import Optional

# Third-party imports
from pydantic import ValidationError
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTCompanyProfileUpdateRequestInvalidName,
    MTCompanyProfileUpdateRequestInvalidRegistrationNumber,
)
from models.schemas.requests.companies.company_profile_update_request import (
    CompanyProfileUpdateRequest,
)


class TestCompanyProfileUpdateRequest:
    """Tests for what an administrator may send about their own agency."""

    def test_a_name_alone_is_enough(self) -> None:
        """Everything but the trading name is optional.

        Notes:
            An agency founded five minutes ago has no SIRET recorded and no
            address geocoded. Requiring them would make the screen unusable for
            exactly the agency that most needs to fill it in.
        """
        request = CompanyProfileUpdateRequest(name="Aide Domicile Paris")

        assert request.name == "Aide Domicile Paris"
        assert request.registration_number is None
        assert request.contact_email is None
        assert request.address is None
        assert request.is_accepting_applications is True

    def test_a_name_is_stripped(self) -> None:
        """Surrounding space is not part of a trading name."""
        request = CompanyProfileUpdateRequest(name="  Aide Domicile  ")

        assert request.name == "Aide Domicile"

    @pytest.mark.parametrize("value", ["", "   ", None, 42])
    def test_a_missing_or_blank_name_is_refused(self, value: Optional[str]) -> None:
        """**The one field nothing else can work around.**

        Args:
            value (Optional[str]): The rejected ``name``.

        Notes:
            The trading name heads every quote the agency prints and is what an
            applicant picks from on the public list. A blank one is a quote
            from nobody.
        """
        with pytest.raises(MTCompanyProfileUpdateRequestInvalidName):
            CompanyProfileUpdateRequest(name=value)

    @pytest.mark.parametrize("value", ["", "   "])
    def test_a_blank_registration_number_becomes_none(self, value: str) -> None:
        """**The case a form produces on every save.**

        Args:
            value (str): The blank the form submits.

        Notes:
            An untouched input submits ``""``. Storing that would make "no
            SIRET recorded" and "SIRET recorded as nothing" two different
            states that read identically on screen and sort differently in a
            report.
        """
        request = CompanyProfileUpdateRequest(name="Agency", registration_number=value)

        assert request.registration_number is None

    def test_a_registration_number_is_stripped_but_not_checked(self) -> None:
        """Length and checksum are deliberately not validated.

        Notes:
            A SIRET has a defined shape, but agencies exist that have not been
            issued one. Refusing to save the rest of the form over a field the
            law does not require here would be the wrong trade — so the value
            is tidied and kept.
        """
        request = CompanyProfileUpdateRequest(
            name="Agency", registration_number="  12345  "
        )

        assert request.registration_number == "12345"

    @pytest.mark.parametrize("value", [42, [], {}])
    def test_a_non_string_registration_number_is_refused(self, value: object) -> None:
        """Tidying is not the same as accepting anything.

        Args:
            value (object): The rejected ``registration_number``.
        """
        with pytest.raises(MTCompanyProfileUpdateRequestInvalidRegistrationNumber):
            CompanyProfileUpdateRequest(name="Agency", registration_number=value)

    def test_a_malformed_contact_address_is_refused(self) -> None:
        """It is published to applicants, so it has to be reachable."""
        with pytest.raises(ValidationError):
            CompanyProfileUpdateRequest(name="Agency", contact_email="not-an-address")

    @pytest.mark.parametrize(
        "field,value",
        [
            ("id", "company-9"),
            ("created_at", "2020-01-01T00:00:00Z"),
            ("updated_at", "2020-01-01T00:00:00Z"),
        ],
    )
    def test_a_field_the_caller_does_not_own_cannot_be_carried(
        self, field: str, value: str
    ) -> None:
        """**The permission, asserted as the shape of the model.**

        Args:
            field (str): The field somebody might try to smuggle in.
            value (str): What they would set it to.

        Notes:
            ``id`` matters most. The agency changed is the one on the caller's
            own credential, so a payload naming another would otherwise be the
            whole of a cross-tenant write.
        """
        request = CompanyProfileUpdateRequest(**{"name": "Agency", field: value})

        assert not hasattr(request, field)

    def test_only_the_owned_fields_are_serialised(self) -> None:
        """What the route is handed, and nothing else.

        Notes:
            The five legal-identity fields joined the original five when a
            quote had to carry them. They belong on this payload — the
            administrator-gated one — because the agency's legal identity
            is not part of running the week.
        """
        request = CompanyProfileUpdateRequest(name="Agency")

        assert set(request.model_dump()) == {
            "name",
            "registration_number",
            "contact_email",
            "address",
            "is_accepting_applications",
            "legal_form",
            "share_capital",
            "rcs_number",
            "vat_number",
            "phone_number",
        }
