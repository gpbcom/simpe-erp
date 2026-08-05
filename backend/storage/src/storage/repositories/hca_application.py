from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import HcaApplicationStatus
from models.people.hca_application import HcaApplication
from storage.mappers.hca_application_mapper import HcaApplicationMapper
from storage.orm.hca_application_row import HcaApplicationRow
from storage.repositories.base import BaseRepository


class HcaApplicationRepository(BaseRepository[HcaApplicationRow]):
    """Reads and writes assistants' self-submitted applications.

    Attributes:
        mapper (HcaApplicationMapper): Converts between rows and models.

    Notes:
        There is no delete. A decided application is the record of a hiring
        decision, and the question "did we already turn this person down?" is
        one somebody eventually asks.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        resolved_logger = logger if logger else getLogger(__name__)
        super().__init__(
            session=session, row_class=HcaApplicationRow, logger=resolved_logger
        )
        self.mapper = HcaApplicationMapper(logger=resolved_logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        company_id: Optional[str] = None,
        status: Optional[HcaApplicationStatus] = None,
    ) -> Select[Tuple[HcaApplicationRow]]:
        """Build the filtered select shared by the listing methods.

        Args:
            company_id (Optional[str]): Restrict to one company.
            status (Optional[HcaApplicationStatus]): Restrict to one status.

        Returns:
            Select[Tuple[HcaApplicationRow]]: The filtered statement, unordered.
        """
        statement = select(HcaApplicationRow)
        if company_id:
            statement = statement.where(HcaApplicationRow.company_id == company_id)
        if status:
            statement = statement.where(HcaApplicationRow.status == status.value)
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, application: HcaApplication) -> HcaApplication:
        """Store a submitted application.

        Args:
            application (HcaApplication): The application to store.

        Returns:
            HcaApplication: The stored application, carrying its identifier.
        """
        self.logger.info(
            "Recording an application from %s to company %s.",
            application.email,
            application.company_id,
        )
        row = self.mapper.to_row(application)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def get(self, application_id: str) -> Optional[HcaApplication]:
        """Return an application by identifier.

        Args:
            application_id (str): The application to read.

        Returns:
            Optional[HcaApplication]: The application, or ``None`` when absent.
        """
        self.logger.debug("Fetching application %s.", application_id)
        row = await self.session.get(HcaApplicationRow, application_id)
        if row is None:
            self.logger.warning("Application %s does not exist.", application_id)
            return None
        return self.mapper.to_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        company_id: Optional[str] = None,
        status: Optional[HcaApplicationStatus] = None,
    ) -> List[HcaApplication]:
        """Return a page of applications, oldest first.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            company_id (Optional[str]): Restrict to one company.
            status (Optional[HcaApplicationStatus]): Restrict to one status.

        Returns:
            List[HcaApplication]: The matching applications.

        Notes:
            Oldest first, unlike most listings here. This is a queue somebody
            works through, and the person who has been waiting longest should
            be at the top of it.
        """
        self.logger.debug(
            "Listing applications: page=%d company=%s status=%s.",
            page,
            company_id,
            status.value if status else None,
        )
        statement = self._build_query(company_id, status).order_by(
            HcaApplicationRow.created_at
        )
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning(
                "No application matches company=%s status=%s.",
                company_id,
                status.value if status else None,
            )
        return self.mapper.to_models(rows)

    async def pending_for_email(
        self, email: str, company_id: str
    ) -> Optional[HcaApplication]:
        """Return an applicant's outstanding application to one company.

        Args:
            email (str): The applicant's address.
            company_id (str): The company applied to.

        Returns:
            Optional[HcaApplication]: The pending application, or ``None``.

        Notes:
            Scoped to the company deliberately. Somebody may legitimately have
            applications open with two agencies at once, and a global check
            would refuse the second.
        """
        self.logger.debug(
            "Looking for a pending application from %s to company %s.",
            email,
            company_id,
        )
        statement = (
            select(HcaApplicationRow)
            .where(HcaApplicationRow.email == email.strip().lower())
            .where(HcaApplicationRow.company_id == company_id)
            .where(HcaApplicationRow.status == HcaApplicationStatus.PENDING.value)
        )
        row = await self._fetch_one(statement)
        return self.mapper.to_model(row) if row else None

    async def update(self, application: HcaApplication) -> Optional[HcaApplication]:
        """Replace an application's details.

        Args:
            application (HcaApplication): The application to store, carrying
                its identifier.

        Returns:
            Optional[HcaApplication]: The updated application, or ``None`` when
            absent.
        """
        if not application.id:
            self.logger.warning("Cannot update an application with no identifier.")
            return None
        row = await self.session.get(HcaApplicationRow, application.id)
        if row is None:
            self.logger.warning(
                "Cannot update the absent application %s.", application.id
            )
            return None
        self.logger.info(
            "Updating application %s to %s.", application.id, application.status.value
        )
        self.mapper.apply_to_row(row, application)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def count(
        self,
        company_id: Optional[str] = None,
        status: Optional[HcaApplicationStatus] = None,
    ) -> int:
        """Return how many applications match.

        Args:
            company_id (Optional[str]): Restrict to one company.
            status (Optional[HcaApplicationStatus]): Restrict to one status.

        Returns:
            int: The number of matching applications.
        """
        self.logger.debug(
            "Counting applications: company=%s status=%s.",
            company_id,
            status.value if status else None,
        )
        return await self._count(self._build_query(company_id, status))
