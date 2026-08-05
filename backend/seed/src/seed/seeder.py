from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime, timedelta
from logging import Logger, getLogger
from typing import List, Optional

from seed.dataset import Dataset

# Third-party imports
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.companies.company import Company
from models.enums import AccountOrigin, QuoteStatus, UserRole
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.people.hca import Hca
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from storage.orm.company_row import CompanyRow
from storage.orm.intervention_type_row import InterventionTypeRow
from storage.orm.quote_row import QuoteRow
from storage.orm.user_row import UserRow
from storage.repositories.company import CompanyRepository
from storage.repositories.customer import CustomerRepository
from storage.repositories.hca import HcaRepository
from storage.repositories.intervention_type import InterventionTypeRepository
from storage.repositories.quote import QuoteRepository
from storage.repositories.user import UserRepository


class Seeder:
    """Fills an empty database with a working agency, and leaves a full one be.

    Attributes:
        session (AsyncSession): The session every write runs on.
        data (Dataset): The fixed contents to write.
        hasher: The password hasher, taken from the authentication service.
        logger (Logger): Logger for seeding.

    Notes:
        - **Idempotent by identifier, not by count.** Every record's primary key
          is derived from its natural key (see
          :meth:`~seed.dataset.Dataset.identifier`), so the seeder asks "does
          this row exist?" and skips it if so. Seeding twice therefore writes
          nothing the second time — which is what lets it run on every
          ``compose up`` without a developer having to remember whether they
          have already done it.
        - It writes through the **repositories**, not raw SQL. The point of
          seeded data is to exercise the same validation the application does; a
          fixture inserted behind the models' backs is exactly the fixture that
          turns out to be impossible to create through the UI.
        - Nothing here geocodes. Every address carries its coordinates, because
          :class:`~models.geo.postal_address.PostalAddress` resolves during
          validation and fifty addresses would be fifty live Nominatim requests.
    """

    def __init__(
        self,
        session: AsyncSession,
        hasher,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the seeder.

        Args:
            session (AsyncSession): The session to write on.
            hasher: An object exposing ``hash(password) -> str``.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.session = session
        self.data = Dataset()
        self.hasher = hasher
        self.logger = logger if logger else getLogger(__name__)
        self.companies = CompanyRepository(session=session, logger=self.logger)
        self.users = UserRepository(session=session, logger=self.logger)
        self.hcas = HcaRepository(session=session, logger=self.logger)
        self.customers = CustomerRepository(session=session, logger=self.logger)
        self.types = InterventionTypeRepository(session=session, logger=self.logger)
        self.quotes = QuoteRepository(session=session, logger=self.logger)
        self.logger.debug("Seeder created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _exists(self, row_class, row_id: str) -> bool:
        """Return whether a row is already stored.

        Args:
            row_class: The ORM class to look in.
            row_id (str): The identifier to look for.

        Returns:
            bool: ``True`` when the row exists.
        """
        found = await self.session.execute(
            select(row_class.id).where(row_class.id == row_id)
        )
        return found.scalar_one_or_none() is not None

    def _address(
        self,
        street: str,
        postal_code: str,
        city: str,
        latitude: float,
        longitude: float,
    ) -> PostalAddress:
        """Build an already-resolved postal address.

        Args:
            street (str): Street line.
            postal_code (str): Postal code.
            city (str): City.
            latitude (float): Resolved latitude.
            longitude (float): Resolved longitude.

        Returns:
            PostalAddress: The address, with nothing left to look up.
        """
        return PostalAddress(
            street=street,
            postal_code=postal_code,
            city=city,
            country="France",
            latitude=latitude,
            longitude=longitude,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def seed_company(self) -> str:
        """Create the agency every other record belongs to.

        Returns:
            str: The company's identifier.
        """
        company_id = self.data.identifier("company", self.data.COMPANY_NAME)
        if await self._exists(CompanyRow, company_id):
            self.logger.debug("Company %s is already seeded.", company_id)
            return company_id
        await self.companies.create(
            Company(
                id=company_id,
                name=self.data.COMPANY_NAME,
                registration_number="812 345 678 00019",
                contact_email="contact@rt-erp.fr",
                address=self._address(
                    "10 rue de la Roquette", "75011", "Paris", 48.8551, 2.3720
                ),
                is_accepting_applications=True,
            )
        )
        self.logger.info("Seeded company %s.", self.data.COMPANY_NAME)
        return company_id

    async def seed_catalog(self) -> List[InterventionType]:
        """Create the service catalog.

        Returns:
            List[InterventionType]: Every catalog entry, seeded or existing.
        """
        stored: List[InterventionType] = []
        for code, name, category, rate in self.data.INTERVENTION_TYPES:
            type_id = self.data.identifier("intervention-type", code)
            if await self._exists(InterventionTypeRow, type_id):
                existing = await self.types.get(type_id)
                if existing is not None:
                    stored.append(existing)
                continue
            stored.append(
                await self.types.create(
                    InterventionType(
                        id=type_id,
                        name=name,
                        code=code,
                        description=f"{name} au domicile du beneficiaire.",
                        service_category=category,
                        base_hourly_rate_ht=self.data.rate_for(code),
                        is_active=True,
                    )
                )
            )
        self.logger.info("Catalog holds %d entries.", len(stored))
        return stored

    async def seed_assistants(self, company_id: str) -> List[Hca]:
        """Create the workforce.

        Args:
            company_id (str): The agency they work for.

        Returns:
            List[Hca]: Every assistant, seeded or existing.
        """
        stored: List[Hca] = []
        for entry in self.data.ASSISTANTS:
            first, last, contract, street, postcode, city, lat, lon, drives = entry
            hca_id = self.data.identifier("hca", f"{first} {last}")
            existing = await self.hcas.get(hca_id)
            if existing is not None:
                stored.append(existing)
                continue
            stored.append(
                await self.hcas.create(
                    Hca(
                        id=hca_id,
                        first_name=first,
                        last_name=last,
                        phone_number=f"+3360000{len(stored):04d}",
                        email=f"{first.lower()}.{last.lower()}@rt-erp.fr",
                        address=self._address(street, postcode, city, lat, lon),
                        company_id=company_id,
                        contract_type=contract,
                        driving_license=(
                            {"categories": ["B"], "number": f"FR{len(stored):08d}"}
                            if drives
                            else None
                        ),
                    )
                )
            )
        self.logger.info("Workforce holds %d assistants.", len(stored))
        return stored

    async def seed_customers(self) -> List[Customer]:
        """Create the people served.

        Returns:
            List[Customer]: Every customer, seeded or existing.
        """
        stored: List[Customer] = []
        for first, last, street, postcode, city, lat, lon in self.data.CUSTOMERS:
            customer_id = self.data.identifier("customer", f"{first} {last}")
            existing = await self.customers.get(customer_id)
            if existing is not None:
                stored.append(existing)
                continue
            stored.append(
                await self.customers.create(
                    Customer(
                        id=customer_id,
                        first_name=first,
                        last_name=last,
                        phone_number=f"+3361000{len(stored):04d}",
                        email=f"{first.lower()}.{last.lower()}@example.fr",
                        address=self._address(street, postcode, city, lat, lon),
                    )
                )
            )
        self.logger.info("Customer book holds %d people.", len(stored))
        return stored

    async def seed_accounts(self, company_id: str, assistants: List[Hca]) -> List[str]:
        """Create the sign-in accounts.

        Args:
            company_id (str): The agency the accounts belong to.
            assistants (List[Hca]): The assistants to bind assistant accounts to.

        Returns:
            List[str]: The addresses that were created, for the printed summary.

        Notes:
            Every account gets the same, known password, and
            ``must_change_password`` is left **false**. A demonstration stack
            whose accounts all demand a password change before showing a single
            screen is a demonstration nobody gets through; the production path
            for a staff-created account still sets the flag.
        """
        created: List[str] = []
        staff = (
            ("admin@rt-erp.fr", "Camille Fournier", UserRole.ADMIN, None),
            ("manager@rt-erp.fr", "Nathalie Blanchard", UserRole.MANAGER, None),
            ("manager2@rt-erp.fr", "Olivier Lefevre", UserRole.MANAGER, None),
        )
        for email, full_name, role, hca_id in staff:
            user_id = self.data.identifier("user", email)
            if await self._exists(UserRow, user_id):
                continue
            await self.users.create(
                _account(
                    user_id=user_id,
                    email=email,
                    full_name=full_name,
                    role=role,
                    hca_id=hca_id,
                    company_id=company_id,
                    hashed=self.hasher.hash(self.data.PASSWORD),
                )
            )
            created.append(email)

        for assistant in assistants:
            email = str(assistant.email)
            user_id = self.data.identifier("user", email)
            if await self._exists(UserRow, user_id):
                continue
            await self.users.create(
                _account(
                    user_id=user_id,
                    email=email,
                    full_name=assistant.full_name(),
                    role=UserRole.HCA,
                    hca_id=assistant.id,
                    company_id=company_id,
                    hashed=self.hasher.hash(self.data.PASSWORD),
                )
            )
            created.append(email)
        self.logger.info("Seeded %d new account(s).", len(created))
        return created

    async def seed_quotes(
        self,
        customers: List[Customer],
        catalog: List[InterventionType],
        author_ids: List[str],
    ) -> int:
        """Create quotes spread across every status.

        Args:
            customers (List[Customer]): The people to quote for.
            catalog (List[InterventionType]): The services to offer.
            author_ids (List[str]): The accounts to attribute quotes to.

        Returns:
            int: How many quotes were written this run.

        Notes:
            The spread matters more than the volume. Every status has to be
            represented or the manager's quote screen cannot be seen doing its
            job — and ``pending-validation`` above all, because that queue is
            the whole point of the validation workflow.
        """
        monday = _monday_of_next_week()
        written = 0
        index = 0
        for status, count in self.data.QUOTE_PLAN:
            for _ in range(count):
                customer = customers[index % len(customers)]
                reference = f"D-{2600 + index:04d}"
                quote_id = self.data.identifier("quote", reference)
                index += 1
                if await self._exists(QuoteRow, quote_id):
                    continue
                await self.quotes.create(
                    _quote(
                        quote_id=quote_id,
                        reference=reference,
                        customer=customer,
                        status=status,
                        author_id=author_ids[index % len(author_ids)]
                        if author_ids
                        else None,
                        lines=_lines(self.data, catalog, monday, index),
                    )
                )
                written += 1
        self.logger.info("Seeded %d new quote(s).", written)
        return written


def _account(
    user_id: str,
    email: str,
    full_name: str,
    role: UserRole,
    hca_id: Optional[str],
    company_id: str,
    hashed: str,
):
    """Build a seeded account.

    Args:
        user_id (str): The derived identifier.
        email (str): The sign-in address.
        full_name (str): The display name.
        role (UserRole): The role to grant.
        hca_id (Optional[str]): The assistant record, for an assistant account.
        company_id (str): The agency.
        hashed (str): The already-hashed password.

    Returns:
        User: The account to store.
    """
    from models.auth.user import User

    return User(
        id=user_id,
        email=email,
        full_name=full_name,
        hashed_password=hashed,
        role=role,
        is_active=True,
        hca_id=hca_id,
        company_id=company_id,
        account_origin=AccountOrigin.SELF_REGISTERED,
        must_change_password=False,
    )


def _quote(
    quote_id: str,
    reference: str,
    customer: Customer,
    status: QuoteStatus,
    author_id: Optional[str],
    lines: List[QuoteLine],
) -> Quote:
    """Build a seeded quote.

    Args:
        quote_id (str): The derived identifier.
        reference (str): The human-facing quote number.
        customer (Customer): Who it is addressed to.
        status (QuoteStatus): Where it sits in its lifecycle.
        author_id (Optional[str]): The account that wrote it.
        lines (List[QuoteLine]): The services offered.

    Returns:
        Quote: The quote to store.
    """
    now = datetime.now(UTC)
    submitted = now if status is QuoteStatus.PENDING_VALIDATION else None
    validated = (
        now
        if status in (QuoteStatus.SENT, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED)
        else None
    )
    return Quote(
        id=quote_id,
        reference=reference,
        customer_id=customer.id,
        status=status,
        lines=lines,
        issued_on=_today() if validated else None,
        valid_until=_today() + timedelta(days=30) if validated else None,
        authored_by=author_id,
        submitted_at=submitted,
        validated_by=author_id if validated else None,
        validated_at=validated,
    )


def _lines(
    data: Dataset,
    catalog: List[InterventionType],
    monday: date,
    seed_index: int,
) -> List[QuoteLine]:
    """Build the lines of one seeded quote.

    Args:
        data (Dataset): The fixed contents, for the service windows.
        catalog (List[InterventionType]): The services to draw from.
        monday (date): The Monday the schedule starts on.
        seed_index (int): Varies the shape from one quote to the next.

    Returns:
        List[QuoteLine]: Between two and four lines, unpriced.

    Notes:
        Left unpriced. The quote service prices on create, against the catalog
        as it stands, which is what an operator's quote goes through — writing
        amounts here would seed figures nothing had computed.
    """
    line_count = 2 + (seed_index % 3)
    days = data.service_days(monday, line_count)
    lines: List[QuoteLine] = []
    for position in range(line_count):
        entry = catalog[(seed_index + position) % len(catalog)]
        start, end, minutes = data.SERVICE_WINDOWS[
            (seed_index + position) % len(data.SERVICE_WINDOWS)
        ]
        lines.append(
            QuoteLine(
                name=entry.name,
                intervention_type_id=entry.id,
                service_date=days[position],
                earliest_start=start,
                latest_end=end,
                duration_minutes=minutes,
            )
        )
    return lines


def _today() -> date:
    """Return today's date in UTC.

    Returns:
        date: Today, read from a timezone-aware clock.

    Notes:
        Read through UTC rather than the machine's local calendar day, so a
        seeder run late in the evening in Paris produces the same dates as one
        run in CI, which lives in UTC. A quote issued "yesterday" on one machine
        and "today" on another is the kind of difference that makes a screenshot
        comparison fail for no real reason.
    """
    return datetime.now(UTC).date()


def _monday_of_next_week() -> date:
    """Return the Monday of the week after this one.

    Returns:
        date: Next Monday.

    Notes:
        The seeded work is in the **future**, so a planning run over it has
        something to place. Seeding last week's visits would produce a
        calendar that is already history and a solver with nothing to do.
    """
    today = _today()
    return today + timedelta(days=7 - today.weekday())
