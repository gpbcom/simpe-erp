from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.companies.company import Company
from storage.mappers.company_mapper import CompanyMapper
from storage.orm.company_row import CompanyRow
from storage.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[CompanyRow]):
    """Reads and writes the agencies an assistant can apply to.

    Attributes:
        mapper (CompanyMapper): Converts between rows and models.

    Notes:
        There is no delete. A company named on an application, an assistant or
        an account cannot be removed without orphaning them, and
        ``is_accepting_applications`` is the honest way to take one off the
        list.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        resolved_logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=CompanyRow, logger=resolved_logger)
        self.mapper = CompanyMapper(logger=resolved_logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(self, accepting_only: bool) -> Select[Tuple[CompanyRow]]:
        """Build the filtered select shared by the listing methods.

        Args:
            accepting_only (bool): Whether to restrict to companies still open
                to applications.

        Returns:
            Select[Tuple[CompanyRow]]: The filtered statement, unordered.
        """
        statement = select(CompanyRow)
        if accepting_only:
            statement = statement.where(CompanyRow.is_accepting_applications.is_(True))
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, company: Company) -> Company:
        """Store a company.

        Args:
            company (Company): The company to store.

        Returns:
            Company: The stored company, carrying its identifier.
        """
        self.logger.info("Creating company %s.", company.name)
        row = self.mapper.to_row(company)
        self.session.add(row)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def get(self, company_id: str) -> Optional[Company]:
        """Return a company by identifier.

        Args:
            company_id (str): The company to read.

        Returns:
            Optional[Company]: The company, or ``None`` when absent.
        """
        self.logger.debug("Fetching company %s.", company_id)
        row = await self.session.get(CompanyRow, company_id)
        if row is None:
            self.logger.warning("Company %s does not exist.", company_id)
            return None
        return self.mapper.to_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        accepting_only: bool = False,
    ) -> List[Company]:
        """Return a page of companies, by name.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            accepting_only (bool): Restrict to those open to applications.

        Returns:
            List[Company]: The matching companies.
        """
        self.logger.debug(
            "Listing companies: page=%d accepting_only=%s.", page, accepting_only
        )
        statement = self._build_query(accepting_only).order_by(CompanyRow.name)
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No company matches accepting_only=%s.", accepting_only)
        return self.mapper.to_models(rows)

    async def update(self, company: Company) -> Optional[Company]:
        """Replace a company's details.

        Args:
            company (Company): The company to store, carrying its identifier.

        Returns:
            Optional[Company]: The updated company, or ``None`` when absent.
        """
        if not company.id:
            self.logger.warning("Cannot update a company with no identifier.")
            return None
        row = await self.session.get(CompanyRow, company.id)
        if row is None:
            self.logger.warning("Cannot update the absent company %s.", company.id)
            return None
        self.logger.info("Updating company %s.", company.id)
        self.mapper.apply_to_row(row, company)
        await self.session.flush()
        return self.mapper.to_model(row)

    async def count(self, accepting_only: bool = False) -> int:
        """Return how many companies match.

        Args:
            accepting_only (bool): Restrict to those open to applications.

        Returns:
            int: The number of matching companies.
        """
        self.logger.debug("Counting companies: accepting_only=%s.", accepting_only)
        return await self._count(self._build_query(accepting_only))
