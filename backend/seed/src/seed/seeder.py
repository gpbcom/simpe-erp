from __future__ import annotations

# Standard library imports
from datetime import UTC, date, datetime, timedelta
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.auth.user import User
from models.catalog.intervention_type import InterventionType
from models.companies.company import Company
from models.enums import AccountOrigin, QuoteStatus, UserRole
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.people.hca import Hca
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from seed.dataset import Dataset  # isort: skip
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
from models.configuration.pricing_config import PricingConfig
from service.quotes.quotes import QuoteService


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
        - **The seeded agency is written directly, not through
          ``POST /api/v1/companies/registration``.** That route generates a
          fresh identifier for the company it founds, and this seeder's whole
          idempotency rests on identifiers derived from natural keys — going
          through it would insert a second agency on every ``compose up``. The
          two paths converge on the same shape: an agency, and one
          administrator account bound to it.
    """

    def __init__(
        self,
        session: AsyncSession,
        hasher,
        pricing: PricingConfig,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the seeder.

        Args:
            session (AsyncSession): The session to write on.
            hasher: An object exposing ``hash(password) -> str``.
            pricing (PricingConfig): The agency's pricing rules, so seeded
                quotes carry the amounts a real one would.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.session = session
        self.data = Dataset()
        self.hasher = hasher
        self.logger = logger if logger else getLogger(__name__)
        self.companies = CompanyRepository(session=session)
        self.users = UserRepository(session=session)
        self.hcas = HcaRepository(session=session)
        self.customers = CustomerRepository(session=session)
        self.types = InterventionTypeRepository(session=session)
        self.quotes = QuoteRepository(session=session)
        # Borrowed from the application, like the hasher above: seeded
        # amounts are computed by the same code an operator's quote goes
        # through, so a seeded quote and a real one cannot disagree about
        # what an hour of care costs.
        self.pricer = QuoteService(
            quotes=self.quotes,
            types=self.types,
            config=pricing,
            logger=self.logger,
        )
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

    def _today(self) -> date:
        """Return today's date in UTC.

        Returns:
            date: Today, read from a timezone-aware clock.

        Notes:
            Read through UTC rather than the machine's local calendar day, so a
            seeder run late in the evening in Paris produces the same dates as
            one run in CI, which lives in UTC. A quote issued "yesterday" on one
            machine and "today" on another is the kind of difference that makes
            a screenshot comparison fail for no real reason.
        """
        return datetime.now(UTC).date()

    def _monday_of_next_week(self) -> date:
        """Return the Monday of the week after this one.

        Returns:
            date: Next Monday.

        Notes:
            The seeded work is in the **future**, so a planning run over it has
            something to place. Seeding last week's visits would produce a
            calendar that is already history and a solver with nothing to do.
        """
        today = self._today()
        return today + timedelta(days=7 - today.weekday())

    def _account(
        self,
        user_id: str,
        email: str,
        full_name: str,
        role: UserRole,
        hca_id: Optional[str],
        company_id: str,
    ) -> User:
        """Build a seeded account.

        Args:
            user_id (str): The derived identifier.
            email (str): The sign-in address.
            full_name (str): The display name.
            role (UserRole): The role to grant.
            hca_id (Optional[str]): The assistant record, for an assistant
                account.
            company_id (str): The agency.

        Returns:
            User: The account to store.
        """
        return User(
            id=user_id,
            email=email,
            full_name=full_name,
            hashed_password=self.hasher.hash(self.data.PASSWORD),
            role=role,
            is_active=True,
            hca_id=hca_id,
            company_id=company_id,
            account_origin=AccountOrigin.SELF_REGISTERED,
            must_change_password=False,
        )

    async def _priced(self, quote: Quote) -> Quote:
        """Return the quote with its lines and weekly totals computed.

        Args:
            quote (Quote): The quote to price.

        Returns:
            Quote: A priced copy.

        Notes:
            Priced through :class:`~service.quotes.quotes.QuoteService`, the
            same code an operator's quote goes through, rather than by writing
            amounts into the dataset. Figures typed into a fixture drift away
            from the catalog the first time a rate changes, and the drift shows
            up as a screen that disagrees with itself.
        """
        catalog = await self.types.get_many(
            [line.intervention_type_id for line in quote.lines]
        )
        return self.pricer.price_quote(quote, catalog)

    def _quote(
        self,
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
            issued_on=self._today() if validated else None,
            valid_until=self._today() + timedelta(days=30) if validated else None,
            authored_by=author_id,
            submitted_at=submitted,
            validated_by=author_id if validated else None,
            validated_at=validated,
        )

    def _lines(
        self,
        catalog: List[InterventionType],
        monday: date,
        seed_index: int,
    ) -> List[QuoteLine]:
        """Build the lines of one seeded quote.

        Args:
            catalog (List[InterventionType]): The services to draw from.
            monday (date): The Monday the schedule starts on.
            seed_index (int): Varies the shape from one quote to the next.

        Returns:
            List[QuoteLine]: Between two and four lines, without amounts.

        Notes:
            The amounts are put on afterwards, by :meth:`_priced`, using the
            application's own pricing rather than figures written here. Leaving
            them off entirely — which this seeder used to do — produces quotes
            that cannot be validated: a quote past ``draft`` with no priced
            lines is refused, so the seeded validation queue looked full and
            every quote in it failed with "has no priced lines".
        """
        line_count = 2 + (seed_index % 3)
        days = self.data.service_days(monday, line_count)
        lines: List[QuoteLine] = []
        for position in range(line_count):
            entry = catalog[(seed_index + position) % len(catalog)]
            start, end, minutes = self.data.SERVICE_WINDOWS[
                (seed_index + position) % len(self.data.SERVICE_WINDOWS)
            ]
            lines.append(
                QuoteLine(
                    name=entry.name,
                    intervention_type_id=entry.id,
                    # Seeded from the catalog entry's own category, which is
                    # what the operator writing the quote would most often
                    # pick. It is a starting point on the line, not a rule:
                    # the same service is necessity care for one customer and
                    # comfort care for another.
                    service_category=entry.service_category,
                    service_date=days[position],
                    earliest_start=start,
                    latest_end=end,
                    duration_minutes=minutes,
                )
            )
        return lines

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
                contact_email="contact@simple-erp.fr",
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
        for code, name, category in self.data.INTERVENTION_TYPES:
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
                        email=f"{first.lower()}.{last.lower()}@simple-erp.fr",
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

    async def seed_accounts(self, company_id: str, assistants: List[Hca]) -> List[str]:  # noqa: E501
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
            ("admin@simple-erp.fr", "Camille Fournier", UserRole.ADMIN, None),
            ("manager@simple-erp.fr", "Nathalie Blanchard", UserRole.MANAGER, None),
            ("manager2@simple-erp.fr", "Olivier Lefevre", UserRole.MANAGER, None),
        )
        for email, full_name, role, hca_id in staff:
            user_id = self.data.identifier("user", email)
            if await self._exists(UserRow, user_id):
                continue
            await self.users.create(
                self._account(
                    user_id=user_id,
                    email=email,
                    full_name=full_name,
                    role=role,
                    hca_id=hca_id,
                    company_id=company_id,
                )
            )
            created.append(email)

        for assistant in assistants:
            email = str(assistant.email)
            user_id = self.data.identifier("user", email)
            if await self._exists(UserRow, user_id):
                continue
            await self.users.create(
                self._account(
                    user_id=user_id,
                    email=email,
                    full_name=assistant.full_name(),
                    role=UserRole.HCA,
                    hca_id=assistant.id,
                    company_id=company_id,
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
        monday = self._monday_of_next_week()
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
                priced = await self._priced(
                    self._quote(
                        quote_id=quote_id,
                        reference=reference,
                        customer=customer,
                        status=status,
                        author_id=author_ids[index % len(author_ids)]
                        if author_ids
                        else None,
                        lines=self._lines(catalog, monday, index),
                    )
                )
                await self.quotes.create(priced)
                written += 1
        self.logger.info("Seeded %d new quote(s).", written)
        return written

    def account_ids_for(self, assistants: List[Hca]) -> List[str]:
        """Return the account identifiers behind the seeded assistants.

        Args:
            assistants (List[Hca]): The seeded assistants.

        Returns:
            List[str]: The account identifiers, so quotes can be attributed to
            real signed-in accounts rather than to nobody.

        Notes:
            A quote's ``authored_by`` is an **account**, not an assistant.
            Seeding it with the assistant's identifier would put every quote
            outside every assistant's own list, because that list filters on
            the account.
        """
        return [
            self.data.identifier("user", str(assistant.email))
            for assistant in assistants
        ]

    def print_credentials(self) -> None:
        """Print the seeded sign-ins.

        Notes:
            Printed rather than logged at ``INFO``, and printed every run rather
            than only when something was written. A developer who reruns the
            stack a week later needs the password on screen, not in a log file
            from the first run.
        """
        password = self.data.PASSWORD
        print()
        print("  SimpleERP is seeded. Sign in at http://localhost:5173 with:")
        print()
        print(f"    Administrator   admin@simple-erp.fr      {password}")
        print(f"    Manager         manager@simple-erp.fr    {password}")
        print(f"    Assistant       luc.martin@simple-erp.fr {password}")
        print()
        print(
            "  Every seeded assistant signs in with firstname.lastname@simple-erp.fr."
        )
        print()
        # Printed because the development stack turns it on and nothing else
        # says so. A developer who does not know the route exists cannot find
        # it: the sign-in card is the only screen that mentions it, and the
        # configuration that opens it is a line in a file they have no reason
        # to read.
        print("  You can also found your own agency from the sign-in card, and")
        print("  be its administrator. Enabled here by")
        print("  auth.allow_company_registration; off in app.yaml.")
        print()
