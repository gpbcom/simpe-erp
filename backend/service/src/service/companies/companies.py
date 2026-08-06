from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional

# First-party imports
from models.companies.company import Company
from models.companies.company_choice import CompanyChoice
from service.companies.exceptions import (
    MTCompanyNameTaken,
    MTCompanyNotEmpty,
    MTCompanyNotFound,
)
from storage.repositories.company import CompanyRepository
from storage.repositories.hca import HcaRepository
from storage.repositories.user import UserRepository


class CompanyService:
    """Manages the agencies an assistant can apply to work for.

    Attributes:
        companies (CompanyRepository): The company store.
        logger (Logger): Logger for company operations.

    Notes:
        - A company is **not** a tenancy boundary in this system. Customers,
          quotes and plannings are agency-wide; what a company scopes is which
          applications a manager may decide. Making it a full tenant would mean
          scoping every query in the application, which is a different piece of
          work and not what "the assistant chooses which company to register
          with" asks for.
        - **Deleting an agency is possible only while it is empty.** Every
          account and every assistant names the agency they belong to, and that
          link is now required rather than optional — so removing an agency
          somebody still points at would leave rows that cannot be rebuilt. An
          agency that has people is closed to applications rather than deleted;
          see :meth:`set_accepting_applications`. What deletion is for is the
          agency that should never have existed: one founded in error, and the
          fixtures a test campaign is obliged to remove after itself.
    """

    def __init__(
        self,
        companies: CompanyRepository,
        users: UserRepository,
        hcas: HcaRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            companies (CompanyRepository): The company store.
            users (UserRepository): The account store, to check an agency is
                empty before removing it.
            hcas (HcaRepository): The assistant store, for the same check.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.companies = companies
        self.users = users
        self.hcas = hcas
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("CompanyService created.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, company: Company) -> Company:
        """Register a company.

        Args:
            company (Company): The company to register.

        Returns:
            Company: The stored company.

        Raises:
            MTCompanyNameTaken: If another company already uses the name.

        Notes:
            The name check happens here rather than being left to the unique
            index, so the answer is a 409 naming the clash rather than a 500
            carrying a constraint name.
        """
        self.logger.info("Registering company %s.", company.name)
        existing = await self.companies.list(size=None)
        if any(item.name.lower() == company.name.lower() for item in existing):
            self.logger.warning(
                "Refused to register %s: the name is already in use.",
                company.name,  # noqa: E501
            )
            raise MTCompanyNameTaken(
                f"A company already trades under {company.name!r}."
            )
        return await self.companies.create(company)

    async def get(self, company_id: str) -> Company:
        """Return one company.

        Args:
            company_id (str): The company to read.

        Returns:
            Company: The company.

        Raises:
            MTCompanyNotFound: If no such company exists.
        """
        self.logger.debug("Reading company %s.", company_id)
        company = await self.companies.get(company_id)
        if company is None:
            self.logger.warning("Company %s does not exist.", company_id)
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        return company

    async def list(self, page: int = 1, size: Optional[int] = None) -> List[Company]:  # noqa: E501
        """Return a page of companies, in full.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[Company]: The companies, including their contact details.

        Notes:
            For authenticated staff. The list an applicant sees comes from
            :meth:`choices`, which carries nothing but names.
        """
        self.logger.debug("Listing companies: page=%d.", page)
        return await self.companies.list(page=page, size=size)

    async def choices(self) -> List[CompanyChoice]:
        """Return the companies an applicant may choose between.

        Returns:
            List[CompanyChoice]: Identifier and name only, for those still
            accepting applications.

        Notes:
            - **Served without a credential, so the shape is the protection.**
              Returning whole companies here would publish a directory of every
              agency's registered office and contact address to anybody who asks;
              :class:`~models.companies.company_choice.CompanyChoice` cannot
              carry them.
            - Companies that have closed their applications are omitted rather
              than shown greyed out: an applicant cannot act on them, and an
              option that fails on submission is worse than one that was never
              offered.
        """
        companies = await self.companies.list(size=None, accepting_only=True)
        self.logger.info("Offering %d company choice(s) to applicants.", len(companies))  # noqa: E501
        if not companies:
            self.logger.warning(
                "No company is accepting applications; the public list is empty."
            )
        return [company.to_public_choice() for company in companies]

    async def update(self, company_id: str, company: Company) -> Company:
        """Replace a company's details.

        Args:
            company_id (str): The company to change.
            company (Company): The new details.

        Returns:
            Company: The updated company.

        Raises:
            MTCompanyNotFound: If no such company exists.

        Notes:
            The identifier comes from the path, not the payload, so a
            well-formed request cannot rewrite a different company than the one
            addressed.
        """
        self.logger.info("Updating company %s.", company_id)
        updated = await self.companies.update(
            company.model_copy(update={"id": company_id})
        )
        if updated is None:
            self.logger.warning("Cannot update the absent company %s.", company_id)  # noqa: E501
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        return updated

    async def set_accepting_applications(
        self, company_id: str, is_accepting: bool
    ) -> Company:
        """Open or close a company to new applications.

        Args:
            company_id (str): The company to change.
            is_accepting (bool): Whether it should appear on the public list.

        Returns:
            Company: The updated company.

        Raises:
            MTCompanyNotFound: If no such company exists.

        Notes:
            Closing does not touch the applications already submitted. Somebody
            who applied yesterday still deserves a decision, and silently
            discarding a queue because the agency stopped advertising would be
            a decision nobody made.
        """
        company = await self.get(company_id)
        self.logger.info(
            "Setting company %s to %s applications.",
            company_id,
            "accept" if is_accepting else "refuse",
        )
        updated = await self.companies.update(
            company.model_copy(update={"is_accepting_applications": is_accepting})  # noqa: E501
        )
        if updated is None:
            self.logger.error(
                "Company %s vanished between the read and the write.",
                company_id,  # noqa: E501
            )
            raise MTCompanyNotFound(f"No company {company_id!r} exists.")
        if not is_accepting:
            self.logger.warning(
                "Company %s no longer appears to applicants; its pending "
                "applications still need deciding.",
                company_id,
            )
        return updated

    async def delete(self, company_id: str) -> None:
        """Remove an agency that nobody belongs to.

        Args:
            company_id (str): The agency to remove.

        Raises:
            MTCompanyNotFound: If no such agency exists.
            MTCompanyNotEmpty: If an account or an assistant still names it.

        Notes:
            The emptiness check names *what* is still attached rather than
            refusing flatly. "Two accounts and one assistant still belong to
            this agency" tells the caller what to do next; "cannot delete"
            leaves them guessing which of three tables to look in.
        """
        await self.get(company_id)
        accounts = await self.users.count_for_company(company_id)
        assistants = await self.hcas.count_for_company(company_id)
        if accounts or assistants:
            self.logger.warning(
                "Refused to delete agency %s: %d account(s) and %d assistant(s) "
                "still belong to it.",
                company_id,
                accounts,
                assistants,
            )
            raise MTCompanyNotEmpty(
                f"Agency {company_id!r} still has {accounts} account(s) and "
                f"{assistants} assistant(s); move or remove them first."
            )
        await self.companies.delete(company_id)
        self.logger.info("Deleted agency %s.", company_id)
