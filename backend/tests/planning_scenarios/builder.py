from __future__ import annotations

# Standard library imports
import zlib
from datetime import date, time
from typing import ClassVar, List, Optional, Tuple

# Third-party imports
from unittest.mock import AsyncMock, MagicMock

# First-party imports
from models.configuration.planning_config import PlanningConfig
from models.enums import AvailabilityKind, ContractType, Weekday
from models.geo.geo_point import GeoPoint
from models.people.hca import Hca
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.hca.certification import Certification
from models.people.hca.skill import Skill
from models.planning.intervention.intervention_requirement import (
    InterventionRequirement,
)
from models.settings.planning_settings import PlanningSettings
from service.planning.plannings import PlanningService


class ScenarioBuilder:
    """Builds realistic planning inputs, so a scenario is a few lines.

    Attributes:
        company_id (str): The agency every built record belongs to.

    Notes:
        - **Every default here is taken from the seeded agency**, not invented.
          The service windows are
          :attr:`~seed.dataset.Dataset.SERVICE_WINDOWS`; the coordinates are
          central Paris, a few hundred metres apart, like the seeded customers.
          That matters more than it looks: a visit whose window is the whole
          working day is a far harder search than any real one, and an instance
          built from such visits makes the solver look slow at a problem nobody
          has. The two bad benchmarks this package exists to prevent were both
          that mistake.
        - The builder deliberately has no ``solve`` method. Construction and
          execution are separated so the catalogue can describe an instance
          without deciding how it is run, and the performance workload can run
          the same instance a different way.
    """

    #: (window start, window end, duration), all in minutes from midnight.
    #:
    #: The seeded agency's five service windows. Narrow, and each visit fits
    #: its own window with an hour or two of slack — which is what makes a
    #: real week tractable and a synthetic one with open windows not.
    WINDOWS: ClassVar[Tuple[Tuple[int, int, int], ...]] = (
        (9 * 60, 11 * 60, 60),
        (9 * 60, 12 * 60, 90),
        (11 * 60 + 30, 14 * 60, 60),
        (14 * 60, 17 * 60, 60),
        (16 * 60, 19 * 60, 90),
    )

    #: Where an assistant lives. Every ``nearby`` point is minutes away.
    HOME: ClassVar[GeoPoint] = GeoPoint(latitude=48.8566, longitude=2.3522)

    #: Far enough to fall outside any sane intervention radius.
    FAR_AWAY: ClassVar[GeoPoint] = GeoPoint(latitude=43.2965, longitude=5.3698)

    #: A Monday, so day-of-week scenarios read the way they are written.
    MONDAY: ClassVar[date] = date(2026, 8, 3)

    def __init__(self, company_id: str = "company-1") -> None:
        """Initialize the builder.

        Args:
            company_id (str): The agency every built record belongs to.
        """
        self.company_id = company_id

    ############################
    # Internal Helpers Methods #
    ############################

    def _offset(self, index: int) -> GeoPoint:
        """Return a point a short, deterministic distance from home.

        Args:
            index (int): Which point in the ring.

        Returns:
            GeoPoint: A point in central Paris, minutes from :attr:`HOME`.

        Notes:
            - Derived from the index rather than drawn at random, because a
              benchmark that moves between runs cannot be compared between
              runs. Two co-prime multipliers keep successive points from
              landing in a line, which would make travel unrealistically cheap.
            - **The index must not come from ``hash()``.** It did, and the
              catalogue caught it: Python randomises string hashing per
              process, so the visits moved between runs while staying fixed
              within one. Every solve was self-consistent and no two runs
              agreed — which is indistinguishable from the solver
              non-determinism this work exists to remove, and would have been
              blamed on it.
        """
        return GeoPoint(
            latitude=self.HOME.latitude + (index % 7) * 0.004,
            longitude=self.HOME.longitude + (index % 5) * 0.006,
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def assistant(
        self,
        hca_id: str = "hca-1",
        skills: Optional[List[Skill]] = None,
        certifications: Optional[List[Certification]] = None,
        working_weekdays: Optional[List[Weekday]] = None,
        availability: Optional[List[AvailabilitySlot]] = None,
        home: Optional[GeoPoint] = None,
        field_employee: bool = True,
        drives: bool = True,
    ) -> Hca:
        """Build one assistant.

        Args:
            hca_id (str): The identifier to assign.
            skills (Optional[List[Skill]]): Skills they have declared.
            certifications (Optional[List[Certification]]): Qualifications.
            working_weekdays (Optional[List[Weekday]]): The recurring week.
                Defaults to every day, so a scenario that does not care about
                the rota does not have to say so.
            availability (Optional[List[AvailabilitySlot]]): Dated absences.
            home (Optional[GeoPoint]): Where they start and end the day.
                ``None`` uses :attr:`HOME`.
            field_employee (bool): Whether they may be scheduled at all.
            drives (bool): Whether they hold a licence, which sets their
                travel speed.

        Returns:
            Hca: The assistant, with a home already geocoded.

        Notes:
            The address carries its coordinates, so nothing here geocodes.
            :class:`~models.geo.postal_address.PostalAddress` resolves during
            validation, and a builder that omitted them would make every test
            a live Nominatim request.
        """
        location = home if home is not None else self.HOME
        return Hca(
            company_id=self.company_id,
            id=hca_id,
            first_name="Test",
            last_name=hca_id.upper(),
            phone_number="+33612345678",
            email=f"{hca_id}@example.com",
            address={
                "street": "1 rue de Rivoli",
                "postal_code": "75001",
                "city": "Paris",
                "latitude": location.latitude,
                "longitude": location.longitude,
            },
            contract_type=ContractType.CDI,
            driving_license={"categories": ["B"]} if drives else None,
            skills=skills or [],
            certifications=certifications or [],
            working_weekdays=working_weekdays or list(Weekday),
            availability=availability or [],
            field_employee=field_employee,
        )

    def homeless_assistant(self, hca_id: str = "hca-lost") -> Hca:
        """Build an assistant whose home never resolved to coordinates.

        Args:
            hca_id (str): The identifier to assign.

        Returns:
            Hca: An assistant the router cannot place.

        Notes:
            Its own method because the address has to be constructed without
            coordinates, which the ordinary :meth:`assistant` deliberately
            cannot do. Such a record is banned from every requirement
            outright — travel from an unknown point is not estimable — and
            that ban is worth a scenario of its own.
        """
        return Hca(
            company_id=self.company_id,
            id=hca_id,
            first_name="Test",
            last_name=hca_id.upper(),
            phone_number="+33612345678",
            email=f"{hca_id}@example.com",
            address={
                "street": "1 rue Introuvable",
                "postal_code": "75001",
                "city": "Paris",
            },
            contract_type=ContractType.CDI,
            driving_license={"categories": ["B"]},
        )

    def requirement(
        self,
        requirement_id: str = "req-1",
        day: Optional[date] = None,
        window: int = 0,
        customer_id: Optional[str] = None,
        location: Optional[GeoPoint] = None,
        skill_codes: Optional[List[str]] = None,
        certification_codes: Optional[List[str]] = None,
        duration_minutes: Optional[int] = None,
    ) -> InterventionRequirement:
        """Build one piece of accepted work.

        Args:
            requirement_id (str): The identifier to assign.
            day (Optional[date]): The day it happens. Defaults to
                :attr:`MONDAY`.
            window (int): Which of :attr:`WINDOWS` to use.
            customer_id (Optional[str]): Whose work it is. Defaults to one
                customer per requirement, so nothing conflicts by accident.
            location (Optional[GeoPoint]): Where it happens. Defaults to a
                point minutes from home.
            skill_codes (Optional[List[str]]): Skills the work requires.
            certification_codes (Optional[List[str]]): Qualifications needed.
            duration_minutes (Optional[int]): How long it takes. Defaults to
                the window's own duration, which is what keeps the instance
                feasible.

        Returns:
            InterventionRequirement: The work, as the solver sees it.

        Notes:
            The codes arrive **already resolved** — the solver never sees the
            catalogue or the inherit-or-override rule, which is settled in
            :meth:`~service.planning.plannings.PlanningService.build`. A
            scenario asserting on inheritance therefore belongs with the
            quote-line tests, not here.
        """
        start, end, default_duration = self.WINDOWS[window % len(self.WINDOWS)]
        index = zlib.crc32(requirement_id.encode("utf-8")) % 35
        return InterventionRequirement(
            id=requirement_id,
            quote_line_id=f"line-{requirement_id}",
            customer_id=customer_id or f"customer-{requirement_id}",
            name="Aide a la toilette",
            intervention_type_id="type-1",
            day=day or self.MONDAY,
            window_start_minute=start,
            window_end_minute=end,
            duration_minutes=duration_minutes or default_duration,
            location=location if location is not None else self._offset(index),
            required_skill_codes=skill_codes or [],
            required_certification_codes=certification_codes or [],
        )

    def absence(
        self,
        hca_id: str,
        day: date,
        start_time: Optional[time] = None,
        end_time: Optional[time] = None,
    ) -> AvailabilitySlot:
        """Build one declared absence.

        Args:
            hca_id (str): Whose absence it is.
            day (date): The day it covers, start and end.
            start_time (Optional[time]): When it starts. ``None`` on both
                times makes it a whole day.
            end_time (Optional[time]): When it ends.

        Returns:
            AvailabilitySlot: The absence.

        Notes:
            The whole-day and partial-day cases are the same model but two
            different constraints — one bans the day outright, the other
            becomes a fixed interval inside the assistant's no-overlap so the
            rest of the day stays usable. Both need a scenario.
        """
        return AvailabilitySlot(
            hca_id=hca_id,
            start_date=day,
            end_date=day,
            kind=AvailabilityKind.HOLIDAY,
            start_time=start_time,
            end_time=end_time,
        )

    def settings(self, radius_km: float = 200.0) -> PlanningSettings:
        """Build the manager-owned rules.

        Args:
            radius_km (float): How far an assistant may be sent from home.
                Wide by default, so a scenario that is not about the radius
                is not quietly constrained by it.

        Returns:
            PlanningSettings: The rules in force.
        """
        return PlanningSettings(max_intervention_radius_km=radius_km)

    def service(self, config: PlanningConfig) -> PlanningService:
        """Build a planning service over stand-in repositories.

        Args:
            config (PlanningConfig): The planning rules.

        Returns:
            PlanningService: A service whose solver is real and whose
            storage is not.

        Notes:
            Every repository is a ``MagicMock`` because these scenarios
            exercise the model, not the round trip. The one that matters is
            ``settings``: :meth:`PlanningService.solve` overwrites
            ``self.settings`` with the value object it is passed, so the
            repository handed in here is never called during a solve.
        """
        return PlanningService(
            runs=MagicMock(),
            interventions=MagicMock(),
            quotes=MagicMock(),
            customers=MagicMock(),
            hcas=MagicMock(),
            types=MagicMock(),
            settings=MagicMock(),
            teams=AsyncMock(),
            config=config,
        )
