from __future__ import annotations

# Standard library imports
from datetime import datetime, timezone

# Third-party imports
import pytest

# First-party imports
from models.organisation.team import TeamDocument
from models.organisation.team.exceptions import (
    MTTeamDocumentInvalidCompanyId,
    MTTeamDocumentInvalidContentType,
    MTTeamDocumentInvalidDate,
    MTTeamDocumentInvalidDocumentKey,
    MTTeamDocumentInvalidFileName,
    MTTeamDocumentInvalidId,
    MTTeamDocumentInvalidSizeBytes,
    MTTeamDocumentInvalidTeamId,
    MTTeamDocumentInvalidUploadedBy,
)
from tests.annotations import ModelInput


def _document(**overrides: ModelInput) -> TeamDocument:
    """Return a valid team document, with any field replaced.

    Args:
        **overrides (ModelInput): Fields to replace on the fixture.

    Returns:
        TeamDocument: The document, built from the overridden values.
    """
    fields = {
        "team_id": "team-1",
        "company_id": "company-1",
        "file_name": "protocole.pdf",
        "content_type": "application/pdf",
        "size_bytes": 2048,
        "document_key": "team-documents/team-1/abc.pdf",
        "uploaded_by": "user-1",
        "uploaded_by_name": "Luc Martin",
    }
    fields.update(overrides)
    return TeamDocument(**fields)


class TestTeamDocument:
    """Tests for the TeamDocument model."""

    # ------------------------------------------------------------------ #
    #  Construction
    # ------------------------------------------------------------------ #

    def test_minimal_valid_construction(self) -> None:
        """A document records what it is, where it is and who added it."""
        document = _document()
        assert document.team_id == "team-1"
        assert document.file_name == "protocole.pdf"
        assert document.size_bytes == 2048
        assert document.document_key.startswith(TeamDocument.KEY_PREFIX)

    def test_no_url_is_stored(self) -> None:
        """The key is stored, never a URL.

        Notes:
            A team's documents are the agency's private paperwork. A public URL
            would make them readable by anybody who is sent one, for ever,
            whatever the application later decided about permissions.
        """
        assert "url" not in TeamDocument.model_fields

    # ------------------------------------------------------------------ #
    #  identifier validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_id",
        [
            pytest.param("", id="Invalid - empty"),
            pytest.param("  ", id="Invalid - whitespace only"),
            pytest.param(3, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_id_is_refused(self, invalid_id: ModelInput) -> None:
        """A present identifier must be a non-empty string."""
        with pytest.raises(MTTeamDocumentInvalidId):
            _document(id=invalid_id)

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            pytest.param("team_id", MTTeamDocumentInvalidTeamId, id="team"),
            pytest.param("company_id", MTTeamDocumentInvalidCompanyId, id="company"),
        ],
    )
    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param(4, id="Invalid - not a string"),
        ],
    )
    def test_the_owning_links_are_required(
        self, field: str, expected: type, invalid_value: ModelInput
    ) -> None:
        """A document belonging to nothing cannot be listed or removed."""
        with pytest.raises(expected):
            _document(**{field: invalid_value})

    # ------------------------------------------------------------------ #
    #  file_name validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_name",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace only"),
            pytest.param(8, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_file_name_is_refused(self, invalid_name: ModelInput) -> None:
        """A file nobody can name is a file nobody can ask for."""
        with pytest.raises(MTTeamDocumentInvalidFileName):
            _document(file_name=invalid_name)

    @pytest.mark.parametrize(
        "path_like",
        [
            pytest.param("../../etc/passwd", id="Invalid - parent traversal"),
            pytest.param("dossier/note.pdf", id="Invalid - forward slash"),
            pytest.param("dossier\\note.pdf", id="Invalid - backslash"),
        ],
    )
    def test_a_file_name_carrying_a_path_is_refused_not_repaired(
        self, path_like: ModelInput
    ) -> None:
        """A separator is refused rather than stripped.

        Notes:
            The name is echoed into a ``Content-Disposition`` header and
            rendered as a link. A value quietly stripped of its ``../`` is a
            value somebody meant to be dangerous — worth a refusal somebody
            sees rather than a repair nobody does.
        """
        with pytest.raises(MTTeamDocumentInvalidFileName):
            _document(file_name=path_like)

    def test_a_file_name_past_the_limit_is_refused(self) -> None:
        """One character over the bound is refused."""
        with pytest.raises(MTTeamDocumentInvalidFileName):
            _document(file_name="f" * (TeamDocument.MAX_FILE_NAME_LENGTH + 1))

    # ------------------------------------------------------------------ #
    #  content_type validation
    # ------------------------------------------------------------------ #

    def test_the_content_type_is_lower_cased(self) -> None:
        """A media type read off a header arrives in any case."""
        assert _document(content_type="Application/PDF").content_type == (
            "application/pdf"
        )

    @pytest.mark.parametrize(
        "invalid_type",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("pdf", id="Invalid - no subtype"),
            pytest.param("/pdf", id="Invalid - no type"),
            pytest.param("application/", id="Invalid - no subtype after slash"),
            pytest.param("a/b/c", id="Invalid - two slashes"),
            pytest.param(1, id="Invalid - not a string"),
        ],
    )
    def test_a_malformed_content_type_is_refused(
        self, invalid_type: ModelInput
    ) -> None:
        """A stored record must carry something a browser can be handed."""
        with pytest.raises(MTTeamDocumentInvalidContentType):
            _document(content_type=invalid_type)

    # ------------------------------------------------------------------ #
    #  size_bytes validation
    # ------------------------------------------------------------------ #

    def test_a_numeric_string_is_accepted(self) -> None:
        """A store may hand the size back as text."""
        assert _document(size_bytes="4096").size_bytes == 4096

    @pytest.mark.parametrize(
        "invalid_size",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param(0, id="Invalid - empty object"),
            pytest.param(-1, id="Invalid - negative"),
            pytest.param("large", id="Invalid - not a number"),
            pytest.param(True, id="Invalid - a boolean"),
        ],
    )
    def test_a_malformed_size_is_refused(self, invalid_size: ModelInput) -> None:
        """Zero is refused too.

        Notes:
            An empty object is not a document somebody meant to share, and the
            object store refuses an empty payload one layer down — a record
            claiming zero bytes could only come from a write that went wrong.
        """
        with pytest.raises(MTTeamDocumentInvalidSizeBytes):
            _document(size_bytes=invalid_size)

    # ------------------------------------------------------------------ #
    #  document_key validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize(
        "invalid_key",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("invoices/2026/INV-1.pdf", id="Invalid - another prefix"),
            pytest.param("hca-photos/x.png", id="Invalid - the portrait prefix"),
            pytest.param(7, id="Invalid - not a string"),
        ],
    )
    def test_a_key_outside_the_team_prefix_is_refused(
        self, invalid_key: ModelInput
    ) -> None:
        """The key is what an authenticated download resolves.

        Notes:
            One pointing outside this prefix would let a stored record address
            any object in the bucket — the invoices among them.
        """
        with pytest.raises(MTTeamDocumentInvalidDocumentKey):
            _document(document_key=invalid_key)

    # ------------------------------------------------------------------ #
    #  uploader validation
    # ------------------------------------------------------------------ #

    @pytest.mark.parametrize("field", ["uploaded_by", "uploaded_by_name"])
    @pytest.mark.parametrize(
        "invalid_value",
        [
            pytest.param(None, id="Invalid - missing"),
            pytest.param("", id="Invalid - empty"),
            pytest.param("   ", id="Invalid - whitespace only"),
            pytest.param(2, id="Invalid - not a string"),
        ],
    )
    def test_both_halves_of_the_uploader_are_required(
        self, field: str, invalid_value: ModelInput
    ) -> None:
        """A file whose uploader is half-recorded is one nobody can ask about."""
        with pytest.raises(MTTeamDocumentInvalidUploadedBy):
            _document(**{field: invalid_value})

    # ------------------------------------------------------------------ #
    #  timestamp validation
    # ------------------------------------------------------------------ #

    def test_the_timestamp_is_parsed_and_serialised(self) -> None:
        """It arrives as text and leaves as ISO-8601."""
        document = _document(created_at="2026-08-12T09:00:00+00:00")
        assert document.created_at == datetime(2026, 8, 12, 9, tzinfo=timezone.utc)
        assert document.model_dump()["created_at"] == "2026-08-12T09:00:00+00:00"

    @pytest.mark.parametrize(
        "invalid_timestamp",
        [
            pytest.param("soon", id="Invalid - unparseable"),
            pytest.param(3, id="Invalid - a number"),
        ],
    )
    def test_a_malformed_timestamp_is_refused(
        self, invalid_timestamp: ModelInput
    ) -> None:
        """Anything that is not a datetime is refused."""
        with pytest.raises(MTTeamDocumentInvalidDate):
            _document(created_at=invalid_timestamp)

    # ------------------------------------------------------------------ #
    #  Behaviour
    # ------------------------------------------------------------------ #

    def test_the_uploader_is_recognised(self) -> None:
        """The uploader may remove their own document."""
        assert _document().was_uploaded_by("user-1")
        assert not _document().was_uploaded_by("user-2")

    def test_an_account_with_no_identifier_uploaded_nothing(self) -> None:
        """``None`` answers ``False`` rather than matching every document."""
        assert not _document().was_uploaded_by(None)
