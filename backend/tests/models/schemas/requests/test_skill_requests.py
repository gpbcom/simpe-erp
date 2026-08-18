from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime

# Third-party imports
import pytest

# First-party imports
from models.people.hca.exceptions import MTSkillInvalidExpiresOn
from models.schemas.exceptions import (
    MTInvalidSkillCreateRequestException,
    MTInvalidSkillTypeUpdateRequestException,
    MTSkillCreateRequestInvalidCode,
    MTSkillCreateRequestInvalidDate,
    MTSkillCreateRequestInvalidIssuer,
    MTSkillCreateRequestInvalidName,
    MTSkillTypeUpdateRequestInvalidDescription,
    MTSkillTypeUpdateRequestInvalidIsActive,
    MTSkillTypeUpdateRequestInvalidLabel,
)
from models.schemas.requests.catalog.skill_type_update_request import (
    SkillTypeUpdateRequest,
)
from models.schemas.requests.hca.skill_create_request import SkillCreateRequest
from tests.annotations import ModelInput


class TestSkillTypeUpdateRequest:
    """Tests for the payload editing a skill-catalogue entry."""

    def test_the_payload_carries_no_code(self) -> None:
        """``code`` is absent, so it cannot be changed at all.

        Notes:
            It is what every declared skill and every service requirement is
            matched on; renaming it would un-skill every holder on the next
            planning run. The screen locks the input, but the rule lives here —
            a locked input is a courtesy, not a control.
        """
        assert "code" not in SkillTypeUpdateRequest.model_fields

    def test_everything_is_optional(self) -> None:
        """An empty payload is a valid no-op, which is what makes it a PATCH."""
        payload = SkillTypeUpdateRequest()
        assert payload.model_dump(exclude_unset=True) == {}

    def test_an_omitted_field_and_a_cleared_one_differ(self) -> None:
        """Clearing a description is a real edit; omitting it is not."""
        cleared = SkillTypeUpdateRequest(description="")
        assert cleared.model_dump(exclude_unset=True) == {"description": ""}
        assert "description" not in SkillTypeUpdateRequest().model_dump(
            exclude_unset=True
        )

    def test_a_label_is_stripped(self) -> None:
        """Leading and trailing space is not part of a display name."""
        assert SkillTypeUpdateRequest(label="  Toilette  ").label == "Toilette"

    @pytest.mark.parametrize("label", ["", "   ", 42])
    def test_a_blank_label_is_refused(self, label: ModelInput) -> None:
        """A blank label shows on screen as an option nobody can identify."""
        with pytest.raises(MTSkillTypeUpdateRequestInvalidLabel):
            SkillTypeUpdateRequest(label=label)

    def test_a_non_string_description_is_refused(self) -> None:
        """A description is text or nothing."""
        with pytest.raises(MTSkillTypeUpdateRequestInvalidDescription):
            SkillTypeUpdateRequest(description=42)

    @pytest.mark.parametrize("value", ["false", 0, 1, "true"])
    def test_a_non_boolean_is_active_is_refused(self, value: ModelInput) -> None:
        """Strings are refused rather than coerced.

        Notes:
            ``"false"`` is truthy, and a retirement read as "still in use"
            would leave an obsolete skill on offer with nothing on screen to
            say the request had not taken.
        """
        with pytest.raises(MTSkillTypeUpdateRequestInvalidIsActive):
            SkillTypeUpdateRequest(is_active=value)

    def test_is_active_accepts_a_real_boolean(self) -> None:
        """Retiring an entry is one switch."""
        assert SkillTypeUpdateRequest(is_active=False).is_active is False

    @pytest.mark.parametrize(
        "exception",
        [
            MTSkillTypeUpdateRequestInvalidDescription,
            MTSkillTypeUpdateRequestInvalidIsActive,
            MTSkillTypeUpdateRequestInvalidLabel,
        ],
    )
    def test_every_failure_belongs_to_one_family(self, exception: type) -> None:
        """One handler row answers 422 for every member."""
        assert issubclass(exception, MTInvalidSkillTypeUpdateRequestException)


class TestSkillCreateRequest:
    """Tests for the payload an assistant declares a skill with."""

    def test_the_payload_carries_no_owner_and_no_identifier(self) -> None:
        """Both absences are the permission, written as a shape.

        Notes:
            The owning assistant comes from the credential and the identifier
            from the store, so this payload cannot file a declaration against a
            colleague and cannot overwrite an existing row by naming it.
        """
        assert "hca_id" not in SkillCreateRequest.model_fields
        assert "id" not in SkillCreateRequest.model_fields

    def test_only_the_name_is_required(self) -> None:
        """A skill can be declared from its name alone."""
        request = SkillCreateRequest(name="Portugais")
        assert request.name == "Portugais"
        assert request.code is None

    @pytest.mark.parametrize("name", ["", "   ", None, 42])
    def test_a_blank_name_is_refused(self, name: ModelInput) -> None:
        """A declaration with no name is not a record anybody keeps."""
        with pytest.raises(MTSkillCreateRequestInvalidName):
            SkillCreateRequest(name=name)

    def test_the_code_is_upper_cased(self) -> None:
        """Matching is a plain equality test, so normalising happens once."""
        assert SkillCreateRequest(name="x", code=" portugais ").code == "PORTUGAIS"

    def test_a_blank_code_reads_as_not_from_the_catalogue(self) -> None:
        """The form offers a select that may be left empty."""
        assert SkillCreateRequest(name="Bricolage", code="  ").code is None

    @pytest.mark.parametrize("code", [42, "A B", "LEVÉ", "A!"])
    def test_a_malformed_code_is_refused(self, code: ModelInput) -> None:
        """A malformed code would match nothing and quietly qualify nobody."""
        with pytest.raises(MTSkillCreateRequestInvalidCode):
            SkillCreateRequest(name="x", code=code)

    def test_a_code_longer_than_the_catalogue_limit_is_refused(self) -> None:
        """The payload and the catalogue must agree on the key's shape."""
        with pytest.raises(MTSkillCreateRequestInvalidCode):
            SkillCreateRequest(
                name="x", code="A" * (SkillCreateRequest.CODE_MAX_LENGTH + 1)
            )

    @pytest.mark.parametrize("issuer", ["", "   ", 42])
    def test_a_blank_issuer_is_refused(self, issuer: ModelInput) -> None:
        """An issuer is a name or nothing, never an empty string."""
        with pytest.raises(MTSkillCreateRequestInvalidIssuer):
            SkillCreateRequest(name="x", issuer=issuer)

    def test_a_datetime_is_narrowed_to_its_date(self) -> None:
        """A date picker submitting midnight is the honest case."""
        request = SkillCreateRequest(
            name="x", obtained_on=datetime(2024, 3, 1, tzinfo=UTC)
        )
        assert request.obtained_on == date(2024, 3, 1)

    @pytest.mark.parametrize("field", ["obtained_on", "expires_on"])
    def test_a_non_date_is_refused(self, field: str) -> None:
        """One validator covers both dates."""
        with pytest.raises(MTSkillCreateRequestInvalidDate):
            SkillCreateRequest(name="x", **{field: 42})

    def test_to_skill_builds_a_skill_with_no_identifier(self) -> None:
        """The store mints one. A caller-chosen id could collide."""
        skill = SkillCreateRequest(
            name="  Lève-personne  ",
            code="leve-personne",
            issuer="Formation interne",
            obtained_on=date(2024, 3, 1),
            expires_on=date(2027, 3, 1),
        ).to_skill()
        assert skill.id is None
        assert skill.name == "Lève-personne"
        assert skill.code == "LEVE-PERSONNE"
        assert skill.issuer == "Formation interne"
        assert skill.obtained_on == date(2024, 3, 1)
        assert skill.expires_on == date(2027, 3, 1)

    def test_the_date_ordering_rule_is_the_skill_s_own(self) -> None:
        """Repeating it here would give one mistake two different messages.

        Notes:
            The request validates each date's *shape*; whether the expiry
            precedes the acquisition is a rule about the pair, and
            ``Skill.check_dates`` already owns it. So the payload builds and
            the conversion raises.
        """
        request = SkillCreateRequest(
            name="x", obtained_on=date(2026, 1, 1), expires_on=date(2025, 1, 1)
        )
        with pytest.raises(MTSkillInvalidExpiresOn):
            request.to_skill()

    @pytest.mark.parametrize(
        "exception",
        [
            MTSkillCreateRequestInvalidCode,
            MTSkillCreateRequestInvalidDate,
            MTSkillCreateRequestInvalidIssuer,
            MTSkillCreateRequestInvalidName,
        ],
    )
    def test_every_failure_belongs_to_one_family(self, exception: type) -> None:
        """One handler row answers 422 for every member."""
        assert issubclass(exception, MTInvalidSkillCreateRequestException)
