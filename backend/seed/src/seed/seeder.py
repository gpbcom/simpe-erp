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
from models.catalog.certification_type import CertificationType
from models.catalog.intervention_type import InterventionType
from models.catalog.skill_type import SkillType
from models.organisation.companies.company import Company
from models.enums import (
    AccountOrigin,
    QuoteStatus,
    RegistrationStatus,
    UserRole,
)
from models.geo.postal_address import PostalAddress
from models.people.customer import Customer
from models.people.hca import Hca
from models.people.hca.certification import Certification
from models.people.hca.skill import Skill
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine

from seed.dataset import Dataset  # isort: skip
from models.configuration.pricing_config import PricingConfig
from service.organisation.teams import TeamService
from service.quotes.quotes import QuoteService
from storage.orm.auth.user_row import UserRow
from storage.orm.catalog.certification_type_row import CertificationTypeRow
from storage.orm.catalog.intervention_type_row import InterventionTypeRow
from storage.orm.catalog.skill_type_row import SkillTypeRow
from storage.orm.companies.company_row import CompanyRow
from storage.orm.quoting.quote_row import QuoteRow
from storage.repositories.auth.user import UserRepository
from storage.repositories.catalog.certification_type import (
    CertificationTypeRepository,  # noqa: E501
)
from storage.repositories.catalog.intervention_type import (
    InterventionTypeRepository,  # noqa: E501
)
from storage.repositories.catalog.skill_type import SkillTypeRepository
from storage.repositories.companies.company import CompanyRepository
from storage.repositories.people.customer import CustomerRepository
from storage.repositories.people.hca import HcaRepository
from storage.repositories.organisation.agency import AgencyRepository
from storage.repositories.organisation.team import TeamRepository
from storage.repositories.quoting.quote import QuoteRepository


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
        self.certifications = CertificationTypeRepository(session=session)
        self.skills = SkillTypeRepository(session=session)
        self.quotes = QuoteRepository(session=session)
        self.agencies = AgencyRepository(session=session)
        self.teams = TeamRepository(session=session)
        self.team_service = TeamService(
            teams=self.teams,
            agencies=self.agencies,
            users=self.users,
            quotes=self.quotes,
            logger=self.logger,
        )
        self.pricer = QuoteService(
            quotes=self.quotes,
            types=self.types,
            config=pricing,
            teams=self.team_service,
            customers=self.customers,
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
        customer_id: Optional[str] = None,
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
            customer_id (Optional[str]): The household record, for a customer
                account. The model refuses an account that carries both this
                and a staff role, so the two are never set together.

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
            customer_id=customer_id,
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
        company_id: str,
        reference: str,
        customer: Customer,
        status: QuoteStatus,
        author_id: Optional[str],
        lines: List[QuoteLine],
    ) -> Quote:
        """Build a seeded quote.

        Args:
            quote_id (str): The derived identifier.
            company_id (str): The agency offering the work.
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
            if status in (QuoteStatus.SENT, QuoteStatus.ACCEPTED, QuoteStatus.REJECTED)  # noqa: E501
            else None
        )
        return Quote(
            id=quote_id,
            company_id=company_id,
            reference=reference,
            customer_id=customer.id,
            status=status,
            lines=lines,
            issued_on=self._today() if validated else None,
            valid_until=self._today() + timedelta(days=30) if validated else None,  # noqa: E501
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
                    service_category=entry.service_category,
                    service_date=days[position],
                    earliest_start=start,
                    latest_end=end,
                    duration_minutes=minutes,
                )
            )
        return lines

    def _certifications_of(self, full_name: str) -> List[Certification]:
        """Return the qualifications a seeded assistant holds.

        Args:
            full_name (str): The assistant's ``"First Last"`` name.

        Returns:
            List[Certification]: Their qualifications, each carrying the
            catalogue code so the planner can match it.

        Notes:
            No expiry is set. A seeded certificate that lapsed would make the
            planner's behaviour depend on the date the stack was started, and a
            fixture whose meaning changes overnight is one nobody can debug.
        """
        return [
            Certification(
                name=label,
                code=code,
                issuer="Ministere du Travail",
            )
            for holder, code in self.data.ASSISTANT_CERTIFICATIONS
            if holder == full_name
            for entry_code, label in self.data.CERTIFICATIONS
            if entry_code == code
        ]

    def _skills_of(self, full_name: str) -> List[Skill]:
        """Return the skills a seeded assistant has declared.

        Args:
            full_name (str): The assistant's ``"First Last"`` name.

        Returns:
            List[Skill]: Their declarations, each carrying the catalogue code
            so the planner can match it.

        Notes:
            - No identifier is set. The store mints one, exactly as it would
              for a declaration made through the account screen, so a seeded
              skill is deletable through the same route as a real one.
            - No expiry, and no ``issuer``: a skill is self-declared, so there
              is usually nobody who attested it, and a seeded expiry would make
              the planner's behaviour depend on the date the stack was started.
        """
        return [
            Skill(name=label, code=code)
            for holder, code in self.data.ASSISTANT_SKILLS
            if holder == full_name
            for entry_code, label in self.data.SKILLS
            if entry_code == code
        ]

    def _registration_status(self, first: str, last: str) -> RegistrationStatus:  # noqa: E501
        """Return the status one seeded customer is created with.

        Args:
            first (str): Their given name.
            last (str): Their family name.

        Returns:
            RegistrationStatus: ``PROSPECT`` for the named few, ``ACTIVE``
            otherwise.

        Notes:
            Keyed by name rather than by an extra element on the customer
            tuple, matching how the seeded assistants get their managers and
            their qualifications: the variation is a handful of exceptions, and
            widening a forty-row tuple to carry one field for two of them makes
            the other thirty-eight noisier to read.
        """
        full_name = f"{first} {last}"
        self.logger.debug("Choosing a registration status for %s.", full_name)
        if not self.data.PROSPECTS:
            self.logger.error("The dataset names no prospects; none will be seeded.")
        elif full_name in self.data.PROSPECTS:
            self.logger.warning(
                "%s is seeded as a prospect: their work is quotable but nothing "
                "will be planned for them until they are promoted.",
                full_name,
            )
            return RegistrationStatus.PROSPECT
        self.logger.info("%s is seeded as an active customer.", full_name)
        return RegistrationStatus.ACTIVE

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
                vat_number="FR40812345678",
                iban="FR7630006000011234567890189",
                bic="AGRIFRPP",
                legal_form="SARL",
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

    async def seed_certifications(self) -> List[CertificationType]:
        """Create the catalogue of qualifications the agency recognises.

        Returns:
            List[CertificationType]: Every entry, seeded or existing.

        Notes:
            Seeded before the workforce, because an assistant's qualification
            names a code and a code that resolves to nothing shows on screen as
            a chip with no label.
        """
        stored: List[CertificationType] = []
        for code, label in self.data.CERTIFICATIONS:
            type_id = self.data.identifier("certification-type", code)
            if await self._exists(CertificationTypeRow, type_id):
                existing = await self.certifications.get(type_id)
                if existing is not None:
                    stored.append(existing)
                continue
            stored.append(
                await self.certifications.create(
                    CertificationType(
                        id=type_id,
                        code=code,
                        label=label,
                        description=f"{label}, reconnu par l'agence.",
                        is_active=True,
                    )
                )
            )
        self.logger.info("Certification catalogue holds %d entries.", len(stored))  # noqa: E501
        return stored

    async def seed_skill_types(self) -> List[SkillType]:
        """Create the catalogue of skills the agency recognises.

        Returns:
            List[SkillType]: Every entry, seeded or existing.

        Notes:
            Seeded before the workforce, for the same reason the certification
            catalogue is: a declared skill names a code, and a code that
            resolves to nothing shows on screen as a chip with no label.
        """
        stored: List[SkillType] = []
        for code, label in self.data.SKILLS:
            type_id = self.data.identifier("skill-type", code)
            if await self._exists(SkillTypeRow, type_id):
                existing = await self.skills.get(type_id)
                if existing is not None:
                    stored.append(existing)
                continue
            stored.append(
                await self.skills.create(
                    SkillType(
                        id=type_id,
                        code=code,
                        label=label,
                        description=f"{label}, reconnu par l'agence.",
                        is_active=True,
                    )
                )
            )
        self.logger.info("Skill catalogue holds %d entries.", len(stored))
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
                            {"categories": ["B"], "number": f"FR{len(stored):08d}"}  # noqa: E501
                            if drives
                            else None
                        ),
                        certifications=self._certifications_of(f"{first} {last}"),  # noqa: E501
                        skills=self._skills_of(f"{first} {last}"),
                    )
                )
            )
        self.logger.info("Workforce holds %d assistants.", len(stored))
        return stored

    async def seed_customers(self) -> List[Customer]:
        """Create the people served.

        Returns:
            List[Customer]: Every customer, seeded or existing.

        Notes:
            **The status is stated, never left to the model's default.** That
            default is now ``PROSPECT`` — a new customer is somebody the agency
            is talking to, not somebody it has agreed to serve — and a seeded
            book that inherited it would be a book the planner refuses to
            schedule anything from. Everyone here is ``ACTIVE`` except the
            handful named in :attr:`~seed.dataset.Dataset.PROSPECTS`, who exist
            so the status filter and the promote button have something real to
            act on.
        """
        stored: List[Customer] = []
        for first, last, street, postcode, city, lat, lon in self.data.CUSTOMERS:  # noqa: E501
            customer_id = self.data.identifier("customer", f"{first} {last}")
            existing = await self.customers.get(customer_id)
            if existing is not None:
                self.logger.debug("Customer %s is already seeded.", customer_id)
                stored.append(existing)
                continue
            stored.append(
                await self.customers.create(
                    Customer(
                        id=customer_id,
                        first_name=first,
                        last_name=last,
                        phone_number=f"+3361000{len(stored):04d}",  # noqa: E501
                        email=f"{first.lower()}.{last.lower()}@example.fr",
                        address=self._address(street, postcode, city, lat, lon),
                        registration_status=self._registration_status(first, last),
                    )
                )
            )
        schedulable = [
            customer
            for customer in stored
            if customer.registration_status.can_be_scheduled()
        ]
        if not schedulable:
            self.logger.error(
                "Not one seeded customer can be scheduled; no planning run will "
                "place anything."
            )
        elif len(schedulable) < len(stored) // 2:
            self.logger.warning(
                "Only %d of %d seeded customers can be scheduled.",
                len(schedulable),
                len(stored),
            )
        self.logger.info(
            "Customer book holds %d people, %d of them schedulable.",
            len(stored),
            len(schedulable),
        )
        return stored

    async def seed_accounts(self, company_id: str, assistants: List[Hca]) -> List[str]:  # noqa: E501
        """Create the sign-in accounts.

        Args:
            company_id (str): The agency the accounts belong to.
            assistants (List[Hca]): The assistants to bind assistant accounts to.

        Returns:
            List[str]: The addresses that were created, for the printed summary.

        Notes:
            - Every account gets the same, known password, and
              ``must_change_password`` is left **false**. A demonstration stack
              whose accounts all demand a password change before showing a single
              screen is a demonstration nobody gets through; the production path
              for a staff-created account still sets the flag.
            - One assistant is seeded **as a manager rather than as an
              assistant** — see
              :attr:`~seed.dataset.Dataset.ASSISTANT_MANAGERS`. The three staff
              accounts hold no assistant record, which is right for a back-office
              manager but left the employment section of the account page
              unreachable in its editable form: it renders from an assistant
              record and unlocks on a manager's role, and no seeded account had
              both. Promoting an existing assistant rather than adding a fourth
              staff account keeps one account per person, so the workforce screen
              still finds exactly one sign-in for them.
        """
        created: List[str] = []
        staff = (
            ("admin@simple-erp.fr", "Camille Fournier", UserRole.ADMIN, None),
            ("manager@simple-erp.fr", "Nathalie Blanchard", UserRole.MANAGER, None),  # noqa: E501
            ("manager2@simple-erp.fr", "Olivier Lefevre", UserRole.MANAGER, None),  # noqa: E501
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
            name = assistant.full_name()
            promoted = name in self.data.ASSISTANT_MANAGERS
            await self.users.create(
                self._account(
                    user_id=user_id,
                    email=email,
                    full_name=name,
                    role=UserRole.MANAGER if promoted else UserRole.HCA,
                    hca_id=assistant.id,
                    company_id=company_id,
                )
            )
            if promoted:
                self.logger.info(
                    "Seeded %s as a manager who still covers rounds.", email
                )
            created.append(email)
        self.logger.info("Seeded %d new account(s).", len(created))
        return created

    async def seed_customer_accounts(
        self, company_id: str, customers: List[Customer]
    ) -> List[str]:
        """Give the named households a sign-in to their own space.

        Args:
            company_id (str): The agency the accounts belong to.
            customers (List[Customer]): Every seeded household.

        Returns:
            List[str]: The addresses that were created, for the printed summary.

        Notes:
            - **Without this there is no way to see the portal at all.** The
              customer role exists, the routes exist and the screens exist, but
              a demonstration stack with no customer account leaves every one of
              them unreachable — which reads as the feature not being there.
            - The address is derived, not taken from the customer record. A
              household's own email is where the agency writes to them, and
              seeding a sign-in under it would mean the demo credentials and the
              contact address are the same string — so changing one on screen
              silently changes what you sign in with.
            - ``must_change_password`` is left **false**, like every other
              seeded account. A real invitation sets it, and
              ``POST /customers/{id}/account`` still does; a demonstration stack
              that demands a password change before showing a single screen is
              a demonstration nobody finishes.
            - Two households rather than all of them, named in
              :attr:`~seed.dataset.Dataset.PORTAL_CUSTOMERS`: one active with
              work on the calendar, one prospect so the empty states are
              reachable without editing anything.
        """
        created: List[str] = []
        wanted = {name for name in self.data.PORTAL_CUSTOMERS}
        self.logger.debug("Seeding portal access for %s.", sorted(wanted))
        if not wanted:
            self.logger.error(
                "No household is named for portal access; the customer space "
                "will be unreachable on this stack."
            )
            return created

        for customer in customers:
            name = customer.full_name()
            if name not in wanted or customer.id is None:
                continue
            email = self.data.portal_email(name)
            user_id = self.data.identifier("user", email)
            if await self._exists(UserRow, user_id):
                continue
            await self.users.create(
                self._account(
                    user_id=user_id,
                    email=email,
                    full_name=name,
                    role=UserRole.CUSTOMER,
                    hca_id=None,
                    company_id=company_id,
                    customer_id=customer.id,
                )
            )
            if not customer.registration_status.can_be_scheduled():
                self.logger.warning(
                    "%s can sign in but is %s, so their space shows no visit "
                    "until a manager promotes them — which is the point of "
                    "seeding one.",
                    email,
                    customer.registration_status.value,
                )
            created.append(email)

        missing = wanted - {c.full_name() for c in customers}
        if missing:
            self.logger.error(
                "PORTAL_CUSTOMERS names %s, which the customer dataset does "
                "not contain; those households get no sign-in.",
                sorted(missing),
            )
        self.logger.info("Seeded %d customer account(s).", len(created))
        return created

    async def seed_quotes(
        self,
        company_id: str,
        customers: List[Customer],
        catalog: List[InterventionType],
        author_ids: List[str],
    ) -> int:
        """Create quotes spread across every status.

        Args:
            company_id (str): The agency offering the work.
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
                        company_id=company_id,
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
        print("  And on the customer side of the sign-in card:")
        print()
        for name in self.data.PORTAL_CUSTOMERS:
            address = self.data.portal_email(name)
            print(f"    Customer        {address:<32} {password}")
        print()
        print(
            "  Every seeded assistant signs in with firstname.lastname@simple-erp.fr."
        )
        print('  A customer must choose "Customer" on the sign-in card: the')
        print("  chooser is validated, so a staff account is refused there and")
        print("  a household is refused on the employee side.")
        print()
        print("  You can also found your own agency from the sign-in card, and")
        print("  be its administrator. Enabled here by")
        print("  auth.allow_company_registration; off in app.yaml.")
        print()
