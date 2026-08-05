from __future__ import annotations

# Standard library imports
from abc import ABC
from logging import Logger, getLogger
from typing import ClassVar, Generic, List, Optional, Sequence, Tuple, Type, TypeVar

# Third-party imports
from sqlalchemy import Select, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from storage.orm.base import Base

RowType = TypeVar("RowType", bound=Base)


class BaseRepository(ABC, Generic[RowType]):
    """Shared read helpers for the ORM-backed repositories.

    Attributes:
        DEFAULT_PAGE_SIZE (ClassVar[int]): Page size used when none is given.
        MAX_PAGE_SIZE (ClassVar[int]): Largest page a caller may request.
        session (AsyncSession): The session every statement runs on.
        row_class (Type[RowType]): The table this repository reads.
        logger (Logger): Logger for repository operations.

    Notes:
        - A repository never commits. The session is handed in already inside a
          transaction owned by
          :meth:`~storage.db.connection_manager.DatabaseConnectionManager.session`,
          so a service that performs several writes gets one transaction rather
          than one per call.
        - Read helpers swallow database errors, log at ``ERROR`` and return an
          empty result; write paths let the error propagate so the surrounding
          transaction rolls back. Silently succeeding on a failed write would be
          far worse than a failed request.
    """

    DEFAULT_PAGE_SIZE: ClassVar[int] = 100
    MAX_PAGE_SIZE: ClassVar[int] = 500

    def __init__(
        self,
        session: AsyncSession,
        row_class: Type[RowType],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            row_class (Type[RowType]): The table this repository reads.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.session = session
        self.row_class = row_class
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug(
            "%s created for table %s.",
            type(self).__name__,
            row_class.__tablename__,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    async def _get_row(self, row_id: str) -> Optional[RowType]:
        """Return a single row by primary key.

        Args:
            row_id (str): The identifier to look up.

        Returns:
            Optional[RowType]: The row, or ``None`` when absent or on error.
        """
        self.logger.debug("Fetching %s row %s.", self.row_class.__tablename__, row_id)
        try:
            return await self.session.get(self.row_class, row_id)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error fetching %s row %s: %s.",
                self.row_class.__tablename__,
                row_id,
                exc,
            )
            return None

    async def _fetch_all(self, statement: Select[Tuple[RowType]]) -> List[RowType]:  # noqa: E501
        """Run a select and return every row it yields.

        Args:
            statement (Select[Tuple[RowType]]): The statement to run.

        Returns:
            List[RowType]: The rows, or an empty list on error.
        """
        try:
            result = await self.session.execute(statement)
            rows: Sequence[RowType] = result.scalars().unique().all()
            self.logger.debug(
                "Fetched %d %s row(s).", len(rows), self.row_class.__tablename__
            )
            return list(rows)
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error fetching %s rows: %s.", self.row_class.__tablename__, exc
            )
            return []

    async def _fetch_one(self, statement: Select[Tuple[RowType]]) -> Optional[RowType]:  # noqa: E501
        """Run a select and return its first row.

        Args:
            statement (Select[Tuple[RowType]]): The statement to run.

        Returns:
            Optional[RowType]: The first row, or ``None`` when there is none or
            on error.
        """
        try:
            result = await self.session.execute(statement)
            return result.scalars().unique().first()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error fetching a %s row: %s.",
                self.row_class.__tablename__,
                exc,  # noqa: E501
            )
            return None

    async def _count(self, statement: Select[Tuple[RowType]]) -> int:
        """Return how many rows a select would yield.

        Args:
            statement (Select[Tuple[RowType]]): The statement to count.

        Returns:
            int: The row count, or ``0`` on error.

        Notes:
            Counting through a subquery keeps the caller's filters intact
            without rebuilding them, so a page total can never disagree with
            the page it describes.
        """
        try:
            counted = select(func.count()).select_from(statement.subquery())
            result = await self.session.execute(counted)
            total = result.scalar_one_or_none()
            return int(total) if total is not None else 0
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error counting %s rows: %s.", self.row_class.__tablename__, exc
            )
            return 0

    def _paginate(
        self,
        statement: Select[Tuple[RowType]],
        page: int,
        size: Optional[int] = None,
    ) -> Select[Tuple[RowType]]:
        """Apply offset and limit to a select.

        Args:
            statement (Select[Tuple[RowType]]): The statement to paginate.
            page (int): One-based page number.
            size (Optional[int]): Page size. Defaults to
                :attr:`DEFAULT_PAGE_SIZE`.

        Returns:
            Select[Tuple[RowType]]: The paginated statement.

        Notes:
            The page number and size are clamped rather than rejected. A
            repository is not the layer that answers a bad request — the
            router validates the query string — and clamping keeps an
            off-by-one in a caller from producing a negative offset, which
            PostgreSQL rejects outright.
        """
        effective_size = size if size else self.DEFAULT_PAGE_SIZE
        effective_size = max(1, min(effective_size, self.MAX_PAGE_SIZE))
        effective_page = max(1, page)
        offset = (effective_page - 1) * effective_size
        self.logger.debug(
            "Paginating %s: page=%d size=%d offset=%d.",
            self.row_class.__tablename__,
            effective_page,
            effective_size,
            offset,
        )
        return statement.offset(offset).limit(effective_size)

    async def _delete_row(self, row_id: str) -> bool:
        """Delete a row by primary key.

        Args:
            row_id (str): The identifier to delete.

        Returns:
            bool: ``True`` when a row was deleted, ``False`` when none matched.

        Raises:
            SQLAlchemyError: If the delete fails — for instance when a foreign
                key still references the row.

        Notes:
            The error is not swallowed. A restricted delete is a meaningful
            answer the caller must map to a 409, not a silent no-op.
        """
        row = await self._get_row(row_id)
        if row is None:
            self.logger.warning(
                "Delete requested for absent %s row %s.",
                self.row_class.__tablename__,
                row_id,
            )
            return False
        await self.session.delete(row)
        await self.session.flush()
        self.logger.info("Deleted %s row %s.", self.row_class.__tablename__, row_id)
        return True
