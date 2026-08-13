from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from typing import ClassVar, List, Tuple
from uuid import NAMESPACE_URL, uuid5

# First-party imports
from models.enums import AgencyType, ContractType, QuoteStatus, ServiceCategory


class Dataset:
    """The fixed contents of the development agency.

    Attributes:
        NAMESPACE (ClassVar[str]): The URL namespace deterministic identifiers
            are derived under.
        COMPANY_NAME (ClassVar[str]): The seeded agency's name.
        PASSWORD (ClassVar[str]): The password every seeded account signs in
            with.
        HOURLY_RATE_HT (ClassVar[str]): The rate every seeded service bills at.
        INTERVENTION_TYPES (ClassVar[Tuple]): The service catalog.
        CERTIFICATIONS (ClassVar[Tuple]): The qualification catalogue.
        SKILLS (ClassVar[Tuple]): The skill catalogue.
        ASSISTANT_SKILLS (ClassVar[Tuple]): Who has declared which skill.
        ASSISTANT_CERTIFICATIONS (ClassVar[Tuple]): Who holds which
            qualification.
        ASSISTANTS (ClassVar[Tuple]): The workforce.
        CUSTOMERS (ClassVar[Tuple]): The people served.
        QUOTE_PLAN (ClassVar[Tuple]): How many quotes to write in each status.
        AGENCIES (ClassVar[Tuple]): The sites the company operates from.
        TEAM_NAME (ClassVar[str]): The one team everybody seeded belongs to.
        TEAM_MANAGER_EMAIL (ClassVar[str]): The account that runs it.

    Notes:
        - **Every identifier is derived, never generated.** ``identifier()``
          hashes a natural key into a UUID5, so the assistant called "Luc
          Martin" gets the same identifier on every run, on every machine. That
          is what makes the seeder an upsert rather than an insert, and it is
          why running it twice changes nothing.
        - **Every address carries its coordinates.**
          :class:`~models.geo.postal_address.PostalAddress` geocodes during
          validation, so seeding forty addresses without them would fire forty
          live requests at Nominatim's public instance and get the machine's IP
          blocked under its usage policy. The coordinates below are real, and
          were looked up once.
        - The data is deliberately French and deliberately plausible: an ERP
          demonstrated with "Test User 1" at "123 Main St" tells a reviewer
          nothing about whether the screens work.
        - **Two sites, but one team.** The Lyon branch exists so the sites
          screen has a second row and so a reviewer can see that a company is
          not its head office — but it holds nobody and no team, and every
          seeded person and quote stays with the Paris team. That is deliberate:
          splitting the seeded workforce would change every count the test
          campaign asserts, and a suite that wants to watch the manager
          narrowing bite forms its own second team through the API and removes
          it afterwards.
    """

    NAMESPACE: ClassVar[str] = "https://simple-erp.fr/seed"
    COMPANY_NAME: ClassVar[str] = "Aide et Presence Paris"
    PASSWORD: ClassVar[str] = "simple-erp-demo-2026"
    HOURLY_RATE_HT: ClassVar[str] = "31.905"

    # (code, name, category)
    INTERVENTION_TYPES: ClassVar[Tuple[Tuple[str, str, ServiceCategory], ...]] = (
        ("TOI", "Aide a la toilette", ServiceCategory.NECESSITY),
        ("REP", "Preparation des repas", ServiceCategory.NECESSITY),
        ("MEN", "Entretien du logement", ServiceCategory.COMFORT),
        ("COU", "Courses et accompagnement", ServiceCategory.COMFORT),
        ("LEV", "Aide au lever et au coucher", ServiceCategory.NECESSITY),
        ("ADM", "Aide administrative", ServiceCategory.COMFORT),
        ("COM", "Compagnie et stimulation", ServiceCategory.COMFORT),
        ("NUI", "Garde de nuit", ServiceCategory.NECESSITY),
    )
    CERTIFICATIONS: ClassVar[Tuple[Tuple[str, str], ...]] = (
        ("DEAES", "Diplome d'Etat d'Accompagnant Educatif et Social"),
        ("DEAVS", "Diplome d'Etat d'Auxiliaire de Vie Sociale"),
        ("ADVF", "Titre professionnel Assistant De Vie aux Familles"),
        ("AS", "Diplome d'Etat d'Aide-Soignant"),
        ("SST", "Sauveteur Secouriste du Travail"),
    )
    SKILLS: ClassVar[Tuple[Tuple[str, str], ...]] = (
        ("LEVE-PERSONNE", "Manipulation d'un leve-personne"),
        ("TOILETTE", "Toilette et aide a l'habillage"),
        ("CUISINE", "Preparation de repas adaptes"),
        ("PORTUGAIS", "Portugais parle"),
        ("ARABE", "Arabe parle"),
        ("ALZHEIMER", "Accompagnement de troubles cognitifs"),
    )
    ASSISTANT_SKILLS: ClassVar[Tuple[Tuple[str, str], ...]] = (
        ("Luc Martin", "LEVE-PERSONNE"),
        ("Luc Martin", "CUISINE"),
        ("Sophie Bernard", "TOILETTE"),
        ("Sophie Bernard", "ALZHEIMER"),
        ("Nadia Bouzid", "ARABE"),
        ("Nadia Bouzid", "TOILETTE"),
    )
    ASSISTANT_CERTIFICATIONS: ClassVar[Tuple[Tuple[str, str], ...]] = (
        ("Luc Martin", "DEAES"),
        ("Luc Martin", "SST"),
        ("Sophie Bernard", "DEAVS"),
        ("Nadia Bouzid", "ADVF"),
    )
    #: The sites the seeded company operates from: ``(name, type, street,
    #: postal code, city, latitude, longitude)``. The head office carries the
    #: company's registered address, so a quote printed from it shows the same
    #: address the company screen does.
    AGENCIES: ClassVar[
        Tuple[Tuple[str, AgencyType, str, str, str, float, float], ...]
    ] = (  # noqa: E501
        (
            "Siege Paris",
            AgencyType.HQ,
            "10 rue de la Roquette",
            "75011",
            "Paris",
            48.8551,
            2.3720,
        ),
        (
            "Antenne Lyon",
            AgencyType.OFFICE,
            "12 rue de la Republique",
            "69002",
            "Lyon",
            45.7640,
            4.8357,
        ),
    )
    #: The one team every seeded person and every seeded quote belongs to.
    TEAM_NAME: ClassVar[str] = "Equipe principale"
    #: The account that runs it. A manager rather than the administrator,
    #: because the manager-facing screens are the ones a reviewer opens.
    TEAM_MANAGER_EMAIL: ClassVar[str] = "manager@simple-erp.fr"

    ASSISTANT_MANAGERS: ClassVar[Tuple[str, ...]] = ("Marc Dubois",)
    ASSISTANTS: ClassVar[Tuple[Tuple, ...]] = (
        (
            "Luc",
            "Martin",
            ContractType.CDI,
            "5 avenue de la Gare",
            "75012",
            "Paris",
            48.8443,
            2.3735,
            True,
        ),
        (
            "Amina",
            "Benali",
            ContractType.CDI,
            "18 rue de Charonne",
            "75011",
            "Paris",
            48.8534,
            2.3776,
            True,
        ),
        (
            "Sophie",
            "Leroy",
            ContractType.CDI,
            "3 rue Oberkampf",
            "75011",
            "Paris",
            48.8646,
            2.3690,
            False,
        ),
        (
            "Marc",
            "Dubois",
            ContractType.CDD,
            "22 rue de Belleville",
            "75020",
            "Paris",
            48.8722,
            2.3795,
            True,
        ),
        (
            "Fatou",
            "Diallo",
            ContractType.CDI,
            "9 rue du Faubourg Saint-Antoine",
            "75011",
            "Paris",
            48.8524,
            2.3719,
            False,
        ),
        (
            "Pierre",
            "Moreau",
            ContractType.CDI,
            "14 boulevard Voltaire",
            "75011",
            "Paris",
            48.8630,
            2.3712,
            True,
        ),
        (
            "Claire",
            "Petit",
            ContractType.CDD,
            "7 rue de Montreuil",
            "75011",
            "Paris",
            48.8517,
            2.3859,
            False,
        ),
        (
            "Karim",
            "Haddad",
            ContractType.CDI,
            "31 rue des Pyrenees",
            "75020",
            "Paris",
            48.8593,
            2.3924,
            True,
        ),
        (
            "Nadia",
            "Rossi",
            ContractType.INTERIM,
            "2 rue de la Roquette",
            "75011",
            "Paris",
            48.8548,
            2.3733,
            False,
        ),
        (
            "Thomas",
            "Girard",
            ContractType.CDI,
            "45 rue de Reuilly",
            "75012",
            "Paris",
            48.8425,
            2.3893,
            True,
        ),
        (
            "Elodie",
            "Fontaine",
            ContractType.CDI,
            "11 rue Crozatier",
            "75012",
            "Paris",
            48.8471,
            2.3805,
            False,
        ),
        (
            "Yassine",
            "Toure",
            ContractType.INTERNSHIP,
            "27 rue de Bagnolet",
            "75020",
            "Paris",
            48.8570,
            2.3970,
            False,
        ),
    )
    PROSPECTS: ClassVar[Tuple[str, ...]] = ("Lucien Guillot", "Renee Berger")
    PORTAL_CUSTOMERS: ClassVar[Tuple[str, ...]] = ("Marie Durand", "Lucien Guillot")
    CUSTOMERS: ClassVar[Tuple[Tuple, ...]] = (
        ("Marie", "Durand", "12 rue de Rivoli", "75004", "Paris", 48.8558, 2.3588),
        ("Jean", "Bernard", "8 rue Saint-Antoine", "75004", "Paris", 48.8543, 2.3646),
        ("Yvette", "Lambert", "40 rue de Turenne", "75003", "Paris", 48.8600, 2.3646),
        ("Robert", "Mercier", "15 rue Amelot", "75011", "Paris", 48.8590, 2.3690),
        ("Simone", "Blanc", "3 rue Keller", "75011", "Paris", 48.8548, 2.3766),
        (
            "Andre",
            "Garnier",
            "21 rue de la Folie-Regnault",
            "75011",
            "Paris",
            48.8586,
            2.3860,
        ),
        ("Denise", "Chevalier", "6 rue Sedaine", "75011", "Paris", 48.8567, 2.3739),
        ("Paul", "Roux", "33 rue Saint-Maur", "75011", "Paris", 48.8639, 2.3773),
        ("Jeanne", "Vincent", "17 rue Popincourt", "75011", "Paris", 48.8577, 2.3760),
        (
            "Michel",
            "Fournier",
            "50 rue de la Fontaine au Roi",
            "75011",
            "Paris",
            48.8676,
            2.3762,
        ),
        ("Colette", "Morel", "2 rue Basfroi", "75011", "Paris", 48.8541, 2.3806),
        ("Henri", "Girault", "9 rue Titon", "75011", "Paris", 48.8512, 2.3856),
        ("Madeleine", "Perrin", "28 rue de Picpus", "75012", "Paris", 48.8420, 2.3936),
        (
            "Georges",
            "Bonnet",
            "11 rue Claude Tillier",
            "75012",
            "Paris",
            48.8480,
            2.3878,
        ),
        ("Lucienne", "Dupuis", "4 rue Erard", "75012", "Paris", 48.8451, 2.3843),
        (
            "Raymond",
            "Leclerc",
            "19 rue de Wattignies",
            "75012",
            "Paris",
            48.8380,
            2.3893,
        ),
        ("Therese", "Guerin", "7 rue Marsoulan", "75012", "Paris", 48.8449, 2.4010),
        ("Albert", "Renaud", "23 rue des Vignoles", "75020", "Paris", 48.8547, 2.3970),
        ("Suzanne", "Barbier", "14 rue Orfila", "75020", "Paris", 48.8672, 2.3944),
        ("Louis", "Marchand", "5 rue des Amandiers", "75020", "Paris", 48.8664, 2.3872),
        ("Odette", "Noel", "38 rue Saint-Blaise", "75020", "Paris", 48.8560, 2.4050),
        ("Rene", "Gauthier", "3 rue de la Chine", "75020", "Paris", 48.8703, 2.3988),
        ("Paulette", "Masson", "16 rue Pelleport", "75020", "Paris", 48.8683, 2.4021),
        ("Marcel", "Robin", "27 avenue Gambetta", "75020", "Paris", 48.8654, 2.3903),
        (
            "Ginette",
            "Aubert",
            "9 rue de Menilmontant",
            "75020",
            "Paris",
            48.8657,
            2.3830,
        ),
        ("Roger", "Meyer", "12 rue Boyer", "75020", "Paris", 48.8697, 2.3898),
        ("Antoinette", "Roy", "6 rue de la Mare", "75020", "Paris", 48.8695, 2.3861),
        (
            "Bernard",
            "Lemoine",
            "44 rue de Charenton",
            "75012",
            "Paris",
            48.8506,
            2.3729,
        ),
        ("Christiane", "Adam", "21 rue Traversiere", "75012", "Paris", 48.8500, 2.3735),
        ("Gilbert", "Weber", "8 rue Hector Malot", "75012", "Paris", 48.8470, 2.3742),
        ("Josette", "Colin", "31 rue Michel Bizot", "75012", "Paris", 48.8378, 2.3987),
        ("Maurice", "Brun", "5 rue Jean Bouton", "75012", "Paris", 48.8452, 2.3760),
        ("Huguette", "Fabre", "18 rue de Lagny", "75020", "Paris", 48.8503, 2.4030),
        ("Jacques", "Poirier", "2 rue Riblette", "75020", "Paris", 48.8592, 2.4060),
        ("Solange", "Legrand", "25 rue de Bagnolet", "75020", "Paris", 48.8572, 2.3962),
        ("Andree", "Millet", "13 rue Planchat", "75020", "Paris", 48.8537, 2.4010),
        (
            "Emile",
            "Charpentier",
            "7 rue Mounet-Sully",
            "75020",
            "Paris",
            48.8524,
            2.4067,
        ),
        ("Yvonne", "Baron", "30 rue des Maraichers", "75020", "Paris", 48.8535, 2.4058),
        (
            "Lucien",
            "Guillot",
            "11 rue de Terre-Neuve",
            "75020",
            "Paris",
            48.8557,
            2.4001,
        ),
        ("Renee", "Berger", "4 rue Ramponeau", "75020", "Paris", 48.8712, 2.3809),
    )

    # (status, how many)
    QUOTE_PLAN: ClassVar[Tuple[Tuple[QuoteStatus, int], ...]] = (
        (QuoteStatus.DRAFT, 8),
        (QuoteStatus.PENDING_VALIDATION, 6),
        (QuoteStatus.SENT, 9),
        (QuoteStatus.ACCEPTED, 26),
        (QuoteStatus.REJECTED, 5),
    )
    SERVICE_WINDOWS: ClassVar[Tuple[Tuple[time, time, int], ...]] = (
        (time(9, 0), time(11, 0), 60),
        (time(9, 0), time(12, 0), 90),
        (time(11, 30), time(14, 0), 60),
        (time(14, 0), time(17, 0), 60),
        (time(16, 0), time(19, 0), 90),
    )

    ############################
    # Publicly Exposed Methods #
    ############################

    def portal_email(self, full_name: str) -> str:
        """Return the sign-in address of a household's portal account.

        Args:
            full_name (str): The household's display name.

        Returns:
            str: The derived address.

        Notes:
            Derived rather than taken from the customer record, and prefixed so
            it cannot collide with a staff address. Seeding the sign-in under
            the household's own contact email would make the demo credentials
            and the address the agency writes to one string — so correcting a
            typo on the customer screen would silently change what you sign in
            with.
        """
        slug = full_name.strip().lower().replace(" ", ".")
        return f"portal.{slug}@simple-erp.fr"

    def identifier(self, kind: str, key: str) -> str:
        """Return the stable identifier for one seeded record.

        Args:
            kind (str): The kind of record, e.g. ``"customer"``.
            key (str): The natural key, e.g. ``"Marie Durand"``.

        Returns:
            str: A UUID derived from the two, identical on every run.

        Notes:
            This is what makes the seeder idempotent. With a random identifier
            each run would insert a second copy of everything, and a developer
            who ran ``compose up`` twice would find eighty customers.
        """
        return str(uuid5(NAMESPACE_URL, f"{self.NAMESPACE}/{kind}/{key}"))

    def rate_for(self, code: str) -> Decimal:
        """Return the hourly rate of one catalog entry.

        Args:
            code (str): The catalog code, e.g. ``"TOI"``.

        Returns:
            Decimal: The rate excluding tax, in EUR per hour.

        Raises:
            KeyError: If the code is not in the catalog.
        """
        for entry_code, _, _ in self.INTERVENTION_TYPES:
            if entry_code == code:
                return Decimal(self.HOURLY_RATE_HT)
        raise KeyError(f"No catalog entry {code!r}.")

    def service_days(self, week_start: date, count: int) -> List[date]:
        """Return consecutive weekdays to schedule work on.

        Args:
            week_start (date): The Monday to start from.
            count (int): How many days to return.

        Returns:
            List[date]: ``count`` weekdays, skipping Saturdays and Sundays.

        Notes:
            Weekends are skipped so the seeded planning looks like a working
            week. The solver would happily place a Sunday visit — the surcharge
            rules exist for exactly that — but a demonstration calendar with
            work on a Sunday reads as a bug rather than as overtime.
        """
        days: List[date] = []
        cursor = week_start
        while len(days) < count:
            if cursor.weekday() < 5:
                days.append(cursor)
            cursor = date.fromordinal(cursor.toordinal() + 1)
        return days
