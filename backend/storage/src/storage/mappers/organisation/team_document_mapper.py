from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, Optional

# First-party imports
from models.organisation.team.team_document import TeamDocument
from storage.mappers.base_mapper import BaseMapper
from storage.orm.organisation.team_document_row import TeamDocumentRow


class TeamDocumentMapper(BaseMapper[TeamDocument, TeamDocumentRow]):
    """Converts between :class:`TeamDocument` and :class:`TeamDocumentRow`.

    Attributes:
        HAS_MODEL_TIMESTAMPS (ClassVar[bool]): The model carries ``created_at``
            and nothing else.

    Notes:
        The model carries only ``created_at`` where the table carries both. A
        stored document is never edited — replacing a file means uploading a new
        one and removing the old, because the object in the store is immutable
        once written — so publishing an ``updated_at`` that always equals the
        creation time would be a field a reader has to work out means nothing.
    """

    HAS_MODEL_TIMESTAMPS: ClassVar[bool] = True

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=TeamDocument, row_class=TeamDocumentRow, logger=logger
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: TeamDocumentRow) -> TeamDocument:
        """Build a document from a row's columns.

        Args:
            row (TeamDocumentRow): The row to read.

        Returns:
            TeamDocument: The domain model.

        Raises:
            MTInvalidTeamDocumentException: If a stored value no longer
                satisfies the model's validators.
        """
        self.logger.debug("Building team document %s from its row.", row.id)
        return TeamDocument(
            id=row.id,
            team_id=row.team_id,
            company_id=row.company_id,
            file_name=row.file_name,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            document_key=row.document_key,
            uploaded_by=row.uploaded_by,
            uploaded_by_name=row.uploaded_by_name,
            created_at=self.timestamps.to_utc(row.created_at),
        )

    def _apply_fields(self, row: TeamDocumentRow, model: TeamDocument) -> None:
        """Write a document's fields onto a row's columns.

        Args:
            row (TeamDocumentRow): The row to write to.
            model (TeamDocument): The model carrying the values.
        """
        self.logger.debug("Applying team document %s to its row.", model.file_name)  # noqa: E501
        row.team_id = model.team_id
        row.company_id = model.company_id
        row.file_name = model.file_name
        row.content_type = model.content_type
        row.size_bytes = model.size_bytes
        row.document_key = model.document_key
        row.uploaded_by = model.uploaded_by
        row.uploaded_by_name = model.uploaded_by_name
