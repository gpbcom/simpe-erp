from __future__ import annotations

# Standard library imports

# Third-party imports
import pytest

# First-party imports
from models.schemas.exceptions import (
    MTCertificationTypeUpdateRequestInvalidDescription,
    MTCertificationTypeUpdateRequestInvalidIsActive,
    MTCertificationTypeUpdateRequestInvalidLabel,
    MTInvalidCertificationTypeUpdateRequestException,
)
from models.schemas.requests.catalog.certification_type_update_request import (
    CertificationTypeUpdateRequest,
)
from tests.annotations import ModelInput


class TestCertificationTypeUpdateRequest:
    """Tests for the payload editing a certification-catalogue entry."""

    # ------------------------------------------------------------------ #
    #  The shape is the permission
    # ------------------------------------------------------------------ #

    def test_the_code_cannot_be_changed(self) -> None:
        """``code`` is absent, so no request can rename it.

        Notes:
            **This test is the rule.** The code is what every stored
            qualification and every intervention type's requirement is matched
            on; renaming it would leave a workforce holding certifications for
            a code that no longer exists and disqualify all of them on the next
            planning run. The screen locks the input, but a locked input is a
            courtesy, not a control.
        """
        assert "code" not in CertificationTypeUpdateRequest.model_fields

    def test_it_carries_only_the_editable_fields(self) -> None:
        """A field added here silently widens what an edit may change."""
        assert set(CertificationTypeUpdateRequest.model_fields) == {
            "label",
            "description",
            "is_active",
        }

    # ------------------------------------------------------------------ #
    #  Sent, cleared, or omitted
    # ------------------------------------------------------------------ #

    def test_an_empty_payload_changes_nothing(self) -> None:
        """Every field is optional, which is what makes this a partial edit."""
        payload = CertificationTypeUpdateRequest()
        assert payload.model_dump(exclude_unset=True) == {}

    def test_only_what_was_sent_is_applied(self) -> None:
        """A label change must not reset the description.

        Notes:
            Optional fields alone cannot tell "not sent" from "set to None", so
            the route reads ``exclude_unset``. Without it, saving a rename
            would silently clear everything else.
        """
        payload = CertificationTypeUpdateRequest(label="Sauveteur")
        assert payload.model_dump(exclude_unset=True) == {"label": "Sauveteur"}

    def test_a_description_can_be_cleared(self) -> None:
        """Emptying the text box is a real edit."""
        payload = CertificationTypeUpdateRequest(description="")
        assert payload.model_dump(exclude_unset=True) == {"description": ""}

    # ------------------------------------------------------------------ #
    #  label validation
    # ------------------------------------------------------------------ #

    def test_the_label_is_stripped(self) -> None:
        """Surrounding whitespace is removed."""
        assert CertificationTypeUpdateRequest(label="  SST  ").label == "SST"

    @pytest.mark.parametrize(
        "invalid_label",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - blank"),
            pytest.param(7, id="Invalid - int"),
        ],
    )
    def test_an_invalid_label_is_refused(self, invalid_label: ModelInput) -> None:
        """An entry with no label shows as a chip nobody can identify."""
        with pytest.raises(MTCertificationTypeUpdateRequestInvalidLabel):
            CertificationTypeUpdateRequest(label=invalid_label)

    # ------------------------------------------------------------------ #
    #  description validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_description",
        [
            pytest.param(7, id="Invalid - int"),
            pytest.param(["text"], id="Invalid - list"),
        ],
    )
    def test_an_invalid_description_is_refused(
        self, invalid_description: ModelInput
    ) -> None:
        """A description that is not text is rejected."""
        with pytest.raises(MTCertificationTypeUpdateRequestInvalidDescription):
            CertificationTypeUpdateRequest(description=invalid_description)

    # ------------------------------------------------------------------ #
    #  is_active validation
    # ------------------------------------------------------------------ #

    def test_an_entry_can_be_retired(self) -> None:
        """Retirement is how an obsolete qualification leaves the catalogue."""
        assert CertificationTypeUpdateRequest(is_active=False).is_active is False

    @pytest.mark.parametrize(
        "invalid_flag",
        [
            pytest.param("false", id="Invalid - string false"),
            pytest.param(0, id="Invalid - int"),
            pytest.param([], id="Invalid - list"),
        ],
    )
    def test_an_invalid_retirement_flag_is_refused(
        self, invalid_flag: ModelInput
    ) -> None:
        """``"false"`` is truthy, so a retirement read as "in use" is refused."""
        with pytest.raises(MTCertificationTypeUpdateRequestInvalidIsActive):
            CertificationTypeUpdateRequest(is_active=invalid_flag)

    # ------------------------------------------------------------------ #
    #  Exception hierarchy
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "exception_class",
        [
            MTCertificationTypeUpdateRequestInvalidDescription,
            MTCertificationTypeUpdateRequestInvalidIsActive,
            MTCertificationTypeUpdateRequestInvalidLabel,
        ],
    )
    def test_exceptions_share_base_class(self, exception_class: type) -> None:
        """Per-field exceptions inherit from the payload's own family base."""
        assert issubclass(
            exception_class, MTInvalidCertificationTypeUpdateRequestException
        )
