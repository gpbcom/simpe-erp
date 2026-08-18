from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.organisation.team.team_document import TeamDocument
from storage.mappers.organisation.team_document_mapper import (
    TeamDocumentMapper,  # noqa: E501
)
from storage.orm.organisation.team_document_row import TeamDocumentRow
from storage.repositories.base import BaseRepository


class TeamDocumentRepository(BaseRepository[TeamDocumentRow]):
    """Reads and writes the index of a team's shared files.

    Attributes:
        mapper (TeamDocumentMapper): Converts between rows and models.

    Notes:
        - This table indexes objects. It does not hold them. The bytes live in
          the object store under the key each row carries, which is why there is
          no update path — a stored object is immutable, so changing a file
          means adding one and removing the other.
        - :meth:`list_keys_for_team` exists for the deletion path. A team's rows
          cascade away with it, and the objects they named would otherwise stay
          in the bucket for ever with nothing left pointing at them.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=TeamDocumentRow)
        self.mapper = TeamDocumentMapper()

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, document: TeamDocument) -> TeamDocument:
        """Record a file that has been written to the object store.

        Args:
            document (TeamDocument): The document to record.

        Returns:
            TeamDocument: The stored record, carrying its identifier.

        Notes:
            Called **after** the upload, never before. A row written first would
            describe an object that may never arrive, and the screen would offer
            a download that answers 503 for ever.
        """
        self.logger.info(
            "Recording document %s in the space of team %s.",
            document.file_name,
            document.team_id,
        )
        row = self.mapper.to_row(document)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def get(self, document_id: str) -> Optional[TeamDocument]:
        """Return a document record by identifier.

        Args:
            document_id (str): The record to read.

        Returns:
            Optional[TeamDocument]: The record, or ``None`` when absent.
        """
        self.logger.debug("Fetching team document %s.", document_id)
        row = await self._get_row(document_id)
        if row is None:
            self.logger.warning("Team document %s does not exist.", document_id)  # noqa: E501
            return None
        return self.mapper.to_model(row)

    async def list_for_team(self, team_id: str) -> List[TeamDocument]:
        """Return a team's files, newest first.

        Args:
            team_id (str): The team whose space is being read.

        Returns:
            List[TeamDocument]: The records, newest first.

        Notes:
            Unpaginated on purpose. A team's shared space is a handful of
            documents rather than a book, and a page control on a list of six is
            a control nobody wants — the index it reads is ``(team_id,
            created_at)`` precisely because this is the only query.
        """
        self.logger.debug("Listing the documents of team %s.", team_id)
        statement = (
            select(TeamDocumentRow)
            .where(TeamDocumentRow.team_id == team_id)
            .order_by(TeamDocumentRow.created_at.desc(), TeamDocumentRow.id)
        )
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.warning("Team %s has no shared document.", team_id)
        return self.mapper.to_models(rows)

    async def count_for_team(self, team_id: str) -> int:
        """Return how many files a team shares.

        Args:
            team_id (str): The team to count for.

        Returns:
            int: The number of documents.
        """
        statement = select(TeamDocumentRow).where(TeamDocumentRow.team_id == team_id)  # noqa: E501
        total = await self._count(statement)
        self.logger.debug("Team %s shares %d document(s).", team_id, total)
        return total

    async def list_keys_for_team(self, team_id: str) -> List[str]:
        """Return the object keys a team's files are stored under.

        Args:
            team_id (str): The team whose space is being emptied.

        Returns:
            List[str]: The keys, ordered.

        Notes:
            Read **before** the team is deleted. Its rows cascade away with it,
            so asking afterwards would find nothing and leave every object
            behind in the bucket with nothing pointing at it — the same reason
            the replan period is measured before a person is removed.
        """
        statement = (
            select(TeamDocumentRow.document_key)
            .where(TeamDocumentRow.team_id == team_id)
            .order_by(TeamDocumentRow.id)
        )
        result = await self.session.execute(statement)
        keys = [row[0] for row in result.all()]
        self.logger.debug("Team %s has %d stored object(s).", team_id, len(keys))  # noqa: E501
        return keys

    async def delete(self, document_id: str) -> bool:
        """Remove a document record.

        Args:
            document_id (str): The record to remove.

        Returns:
            bool: ``True`` when a row was removed.

        Notes:
            The object itself is removed by the service, which owns the store.
            The row goes first: an orphaned object costs storage, where an
            orphaned row costs a download that answers 503.
        """
        self.logger.info("Deleting team document %s.", document_id)
        return await self._delete_row(document_id)
