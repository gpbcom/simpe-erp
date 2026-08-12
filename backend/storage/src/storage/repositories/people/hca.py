from __future__ import annotations

# Standard library imports
from datetime import date
from logging import Logger, getLogger
from typing import List, Optional, Tuple
from uuid import uuid4

# Third-party imports
from sqlalchemy import Select, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.enums import ContractType, Weekday
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.hca.certification import Certification
from models.people.hca.skill import Skill
from models.people.hca import Hca
from models.schemas.requests.hca.hca_filter import HcaFilter
from storage.mappers.people.hca_mapper import HcaMapper
from storage.orm.people.availability_row import AvailabilityRow
from storage.orm.people.certification_row import CertificationRow
from storage.orm.people.hca_row import HcaRow
from storage.orm.people.skill_row import SkillRow
from storage.repositories.base import BaseRepository


class HcaRepository(BaseRepository[HcaRow]):
    """Reads and writes Home Care Assistants.

    Attributes:
        mapper (HcaMapper): Converts between rows and domain models.

    Notes:
        - Three mutation paths are deliberately narrow rather than general.
          :meth:`set_employment` is the only way a manager changes an
          assistant, :meth:`add_availability` the only way an absence is filed,
          and :meth:`add_skill` the only way a skill is declared. A single
          general update would let any of those callers overwrite fields they
          have no business touching.
        - The skill pair appends and removes one row, where the certification
          path replaces the whole list. That difference is the feature: a
          manager edits a form, an assistant adds one thing at a time, and a
          wholesale write on the second path would let a second declaration
          delete the first.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=HcaRow)
        self.mapper = HcaMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(
        self,
        search: Optional[str] = None,
        contract_type: Optional[ContractType] = None,
        hca_filter: Optional[HcaFilter] = None,
        hca_ids: Optional[List[str]] = None,
    ) -> Select[Tuple[HcaRow]]:
        """Build the filtered select shared by ``list`` and ``count``.

        Args:
            search (Optional[str]): Case-insensitive fragment.
            contract_type (Optional[ContractType]): Restrict to one contract.
            hca_filter (Optional[HcaFilter]): The richer filter. Its ``search``
                and ``contract_type`` win over the two positional arguments
                when both are given.
            hca_ids (Optional[List[str]]): The assistants the caller may read.
                ``None`` means every assistant; an **empty list means none**.

        Returns:
            Select[tuple[HcaRow]]: The filtered statement, without ordering or pagination.

        Notes:
            - Shared so a page and its total can never be computed from
              different filters.
            - ``hca_ids`` is a **permission, not a preference**, and it is
              applied in the statement for the reason ``authored_by`` is on the
              quote side: a page of fifty narrowed to three afterwards has
              already read forty-seven records the caller may not see. ``None``
              and ``[]`` mean opposite things, and reading the empty list as
              falsy would show a manager who runs no team the whole workforce.
            - ``search`` and ``contract_type`` survive as parameters because
              other callers still pass them on their own. A caller with an
              :class:`HcaFilter` passes that instead and the two named
              arguments fall away.
        """
        applied = hca_filter or HcaFilter()
        self.logger.debug(
            "Building the assistant query from %s.",
            applied.model_dump(exclude_none=True),
        )
        if hca_filter is not None and search and applied.search:
            # Both were given and they disagree. The filter wins, so say which
            # fragment actually ran rather than leaving the caller to wonder.
            self.logger.warning(
                "Two searches were passed (%r and %r); the filter's %r is used.",
                search,
                applied.search,
                applied.search,
            )
        search = applied.search or search
        contract_type = applied.contract_type or contract_type
        if applied.is_empty() and search is None and contract_type is None:
            self.logger.info("No filter was given; the query is every assistant.")

        statement = select(HcaRow)
        if hca_ids is not None:
            if not hca_ids:
                self.logger.warning(
                    "The caller may read no assistant; the query matches nothing."
                )
            statement = statement.where(HcaRow.id.in_(hca_ids))
        if contract_type is not None:
            statement = statement.where(HcaRow.contract_type == contract_type.value)  # noqa: E501
        if search:
            pattern = f"%{search.strip().lower()}%"
            statement = statement.where(
                or_(
                    HcaRow.first_name.ilike(pattern),
                    HcaRow.last_name.ilike(pattern),
                    HcaRow.email.ilike(pattern),
                    HcaRow.city.ilike(pattern),
                )
            )
        # One column each, unlike ``search``: somebody who has decided the
        # fragment is a postcode does not want it matched against a surname.
        for fragment, column in (
            (applied.city, HcaRow.city),
            (applied.postal_code, HcaRow.postal_code),
            (applied.email, HcaRow.email),
        ):
            if fragment:
                statement = statement.where(
                    column.ilike(f"%{fragment.strip().lower()}%")
                )
        if applied.phone:
            typed = "".join(
                character for character in applied.phone if character.isdigit()
            )
            if not typed:
                # Everything typed was punctuation, so the predicate would be
                # `LIKE '%%'` — every assistant, under a filter that says it is
                # narrowing by telephone number.
                self.logger.error(
                    "Telephone filter %r holds no digit; it is dropped rather "
                    "than matched as a wildcard.",
                    applied.phone,
                )
            if typed:
                statement = statement.where(HcaRow.phone_number.like(f"%{typed}%"))
        if applied.field_employee is not None:
            statement = statement.where(
                HcaRow.field_employee.is_(applied.field_employee)
            )
        if applied.is_geocoded is not None:
            resolved = HcaRow.latitude.is_not(None) & HcaRow.longitude.is_not(None)
            statement = statement.where(resolved if applied.is_geocoded else ~resolved)
        if applied.has_photo is not None:
            has_photo = HcaRow.photo_url.is_not(None)
            statement = statement.where(has_photo if applied.has_photo else ~has_photo)
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, hca: Hca) -> Hca:
        """Insert a new assistant.

        Args:
            hca (Hca): The assistant to store.

        Returns:
            Hca: The stored assistant, carrying its generated identifier.

        Raises:
            SQLAlchemyError: If the insert fails.
        """
        self.logger.info("Creating hca %s.", hca.full_name())
        row = self.mapper.to_row(hca)
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        self.logger.debug("Created hca row %s.", row.id)
        return self.mapper.to_model(row)

    async def get(self, hca_id: str) -> Optional[Hca]:
        """Return an assistant by identifier.

        Args:
            hca_id (str): The identifier to look up.

        Returns:
            Optional[Hca]: The assistant, or ``None`` when absent.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning("Hca %s not found.", hca_id)
            return None
        return self.mapper.to_model(row)

    async def update(self, hca: Hca) -> Optional[Hca]:
        """Update an existing assistant in full.

        Args:
            hca (Hca): The assistant to store, carrying its identifier.

        Returns:
            Optional[Hca]: The updated assistant, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if hca.id is None:
            self.logger.warning("Update requested for an hca with no id.")
            return None
        row = await self._get_row(hca.id)
        if row is None:
            self.logger.warning("Update requested for absent hca %s.", hca.id)
            return None
        self.mapper.apply_to_row(row, hca)
        await self.session.flush()
        await self.session.refresh(row)
        self.logger.info("Updated hca %s.", hca.id)
        return self.mapper.to_model(row)

    async def set_photo_url(
        self, hca_id: str, photo_url: Optional[str]
    ) -> Optional[Hca]:
        """Point an assistant's record at a stored photograph, or clear it.

        Args:
            hca_id (str): The assistant to change.
            photo_url (Optional[str]): The object-store URL, or ``None`` to
                remove the photograph.

        Returns:
            Optional[Hca]: The updated assistant, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.

        Notes:
            A narrow method, like the other mutations here: the photograph is
            uploaded on its own endpoint, and routing it through a general
            update would let a stale payload overwrite the contact details or
            the availability at the same time.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning("Photograph link requested for absent hca %s.", hca_id)
            return None
        self.logger.info("Setting the photograph of hca %s to %s.", hca_id, photo_url)
        row.photo_url = photo_url
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def set_employment(
        self,
        hca_id: str,
        contract_type: ContractType,
        certifications: List[Certification],
        field_employee: bool,
    ) -> Optional[Hca]:
        """Replace an assistant's contract, qualifications and rounds flag.

        Args:
            hca_id (str): The assistant to change.
            contract_type (ContractType): The new employment contract.
            certifications (List[Certification]): The qualifications now held.
            field_employee (bool): Whether this person may be placed on an
                intervention planning.

        Returns:
            Optional[Hca]: The updated assistant, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.

        Notes:
            - These are the only three fields a manager may change. Enforcing
              that through a narrow method — rather than trusting the caller to
              send a partial payload — means no manager-facing route can reach
              the contact details, the home address or the availability.
            - The certifications are replaced wholesale, matching the edit form's
              semantics: what is sent is what the assistant now holds.
            - ``field_employee`` has **no default, deliberately**. It carried
              ``True`` while the flag was new, so that a caller written before
              it existed left people on the rounds rather than withdrawing
              them — and that default long outlived its purpose. The service
              did not forward the value it was sent, so every employment save
              silently re-enabled a person somebody had taken off the rounds,
              and a manager switching it off got a 200 and no change. Requiring
              it makes the same omission a ``TypeError`` at import time rather
              than a wrong row.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning(
                "Employment change requested for absent hca %s.", hca_id
            )
            return None
        self.logger.info(
            "Setting hca %s employment: contract=%s certifications=%d "
            "field_employee=%s.",
            hca_id,
            contract_type.value,
            len(certifications),
            field_employee,
        )
        if row.field_employee and not field_employee:
            self.logger.warning(
                "Assistant %s is no longer a field employee; they will be "
                "left out of every planning run from now on.",
                hca_id,
            )
        row.contract_type = contract_type.value
        row.field_employee = field_employee
        row.certifications = [
            CertificationRow(
                id=str(uuid4()),
                hca_id=hca_id,
                name=certification.name,
                code=certification.code,
                issuer=certification.issuer,
                obtained_on=certification.obtained_on,
                expires_on=certification.expires_on,
            )
            for certification in certifications
        ]
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def set_working_weekdays(
        self, hca_id: str, working_weekdays: List[Weekday]
    ) -> Optional[Hca]:
        """Replace the days of the week an assistant works.

        Args:
            hca_id (str): The assistant to change.
            working_weekdays (List[Weekday]): The days now worked.

        Returns:
            Optional[Hca]: The updated assistant, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.

        Notes:
            - Narrow, like the other mutations here. The working week is the
              assistant's own to set, and routing it through a general update
              would let the same payload rewrite their address.
            - The whole week replaces the stored one. There is no add-a-day
              form of this, because the caller sends what they now work rather
              than a delta against what the server currently believes.
            - A week that shrinks is logged at ``WARNING``. Dropping a day
              silently removes the assistant from every future round on it, and
              the run that then fails to place a visit is easier to explain
              with this line in the log than without it.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning(
                "Working-week change requested for absent hca %s.", hca_id
            )
            return None
        stored = self.mapper.to_model(row).working_weekdays
        dropped = sorted(
            set(stored) - set(working_weekdays),
            key=lambda day: day.iso_weekday(),  # noqa: E501
        )
        if dropped:
            self.logger.warning(
                "Assistant %s no longer works %s; they will be left out of "
                "every planning run on those days.",
                hca_id,
                ", ".join(day.value for day in dropped),
            )
        self.logger.info(
            "Setting the working week of hca %s to %d day(s).",
            hca_id,
            len(working_weekdays),
        )
        row.working_weekdays = self.mapper.weekdays_to_column(working_weekdays)
        await self.session.flush()
        await self.session.refresh(row)
        return self.mapper.to_model(row)

    async def add_skill(self, hca_id: str, skill: Skill) -> Optional[Skill]:
        """Record a skill an assistant declared about themselves.

        Args:
            hca_id (str): The assistant declaring it.
            skill (Skill): The skill to record.

        Returns:
            Optional[Skill]: The stored skill with its generated identifier, or
            ``None`` when the assistant is absent.

        Raises:
            SQLAlchemyError: If the insert fails.

        Notes:
            - **Appends; it does not replace.** This is the opposite of
              :meth:`set_employment`, and deliberately so: a manager sends the
              whole certification list because they are editing a form, while
              an assistant declares one skill at a time from their own screen.
              A replace here would let somebody's second declaration silently
              delete their first.
            - The assistant identifier comes from the argument, never from the
              payload — and :class:`~models.people.hca.skill.Skill` has no
              ``hca_id`` to send, so there is nothing to ignore.
            - The identifier is generated here rather than taken from the
              model. It is what a later delete addresses, and one chosen by a
              caller would be one a caller could point at somebody else's row.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning("Skill declared for absent hca %s.", hca_id)
            return None
        skill_id = str(uuid4())
        self.logger.info(
            "Recording skill %s (%s, code=%s) for hca %s.",
            skill_id,
            skill.name,
            skill.code,
            hca_id,
        )
        if skill.code is None:
            self.logger.warning(
                "Skill %s for hca %s carries no catalogue code; the planner "
                "cannot match any requirement against it.",
                skill_id,
                hca_id,
            )
        skill_row = SkillRow(
            id=skill_id,
            hca_id=hca_id,
            name=skill.name,
            code=skill.code,
            issuer=skill.issuer,
            obtained_on=skill.obtained_on,
            expires_on=skill.expires_on,
        )
        self.session.add(skill_row)
        await self.session.flush()
        self.logger.debug("Stored skill row %s for hca %s.", skill_id, hca_id)
        return skill.model_copy(update={"id": skill_id})

    async def remove_skill(self, hca_id: str, skill_id: str) -> bool:
        """Withdraw a declared skill.

        Args:
            hca_id (str): The assistant the skill belongs to.
            skill_id (str): The skill to withdraw.

        Returns:
            bool: ``True`` when the skill was removed.

        Notes:
            The assistant identifier is part of the lookup, not just the skill
            identifier. Without it, knowing a skill id would be enough to strip
            a colleague of a qualification and quietly take them off every
            visit that requires it — the same reasoning as
            :meth:`remove_availability`, with a larger blast radius.
        """
        statement = select(SkillRow).where(
            SkillRow.id == skill_id,
            SkillRow.hca_id == hca_id,
        )
        try:
            result = await self.session.execute(statement)
            skill_row = result.scalars().first()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error loading skill %s for hca %s: %s.",
                skill_id,
                hca_id,
                exc,
            )
            return False
        if skill_row is None:
            self.logger.warning("Skill %s not found for hca %s.", skill_id, hca_id)
            return False
        if skill_row.code is not None:
            self.logger.warning(
                "Withdrawing skill %s (%s) from hca %s; they will no longer be "
                "eligible for work requiring it.",
                skill_id,
                skill_row.code,
                hca_id,
            )
        await self.session.delete(skill_row)
        await self.session.flush()
        self.logger.info("Removed skill %s for hca %s.", skill_id, hca_id)
        return True

    async def add_availability(
        self, hca_id: str, slot: AvailabilitySlot
    ) -> Optional[AvailabilitySlot]:
        """File an absence for an assistant.

        Args:
            hca_id (str): The assistant the absence belongs to.
            slot (AvailabilitySlot): The absence to record.

        Returns:
            Optional[AvailabilitySlot]: The stored absence with its generated
            identifier, or ``None`` when the assistant is absent.

        Raises:
            SQLAlchemyError: If the insert fails.

        Notes:
            The assistant identifier comes from the argument, never from the
            payload: an assistant must not be able to file an absence against a
            colleague by naming them in the body.
        """
        row = await self._get_row(hca_id)
        if row is None:
            self.logger.warning("Availability filed for absent hca %s.", hca_id)  # noqa: E501
            return None
        slot_id = str(uuid4())
        self.logger.info(
            "Filing %s availability %s for hca %s (%s to %s).",
            slot.kind.value,
            slot_id,
            hca_id,
            slot.start_date,
            slot.end_date,
        )
        slot_row = AvailabilityRow(
            id=slot_id,
            hca_id=hca_id,
            start_date=slot.start_date,
            end_date=slot.end_date,
            kind=slot.kind.value,
            start_time=slot.start_time,
            end_time=slot.end_time,
            note=slot.note,
        )
        self.session.add(slot_row)
        await self.session.flush()
        return slot.model_copy(update={"id": slot_id, "hca_id": hca_id})

    async def remove_availability(self, hca_id: str, slot_id: str) -> bool:
        """Withdraw a filed absence.

        Args:
            hca_id (str): The assistant the absence belongs to.
            slot_id (str): The absence to withdraw.

        Returns:
            bool: ``True`` when the absence was removed.

        Notes:
            The assistant identifier is part of the lookup, not just the slot
            identifier. Without it, knowing a slot id would be enough to delete
            another assistant's absence.
        """
        statement = select(AvailabilityRow).where(
            AvailabilityRow.id == slot_id,
            AvailabilityRow.hca_id == hca_id,
        )
        try:
            result = await self.session.execute(statement)
            slot_row = result.scalars().first()
        except SQLAlchemyError as exc:
            self.logger.error(
                "Error loading availability %s for hca %s: %s.",
                slot_id,
                hca_id,
                exc,
            )
            return False
        if slot_row is None:
            self.logger.warning(
                "Availability %s not found for hca %s.", slot_id, hca_id
            )
            return False
        await self.session.delete(slot_row)
        await self.session.flush()
        self.logger.info("Removed availability %s for hca %s.", slot_id, hca_id)  # noqa: E501
        return True

    async def list_availability(
        self,
        hca_id: str,
        start: Optional[date] = None,
        end: Optional[date] = None,  # noqa: E501
    ) -> List[AvailabilitySlot]:
        """Return an assistant's absences, optionally within a window.

        Args:
            hca_id (str): The assistant to read.
            start (Optional[date]): Earliest day of interest.
            end (Optional[date]): Latest day of interest.

        Returns:
            List[AvailabilitySlot]: The matching absences, oldest first.

        Notes:
            The overlap test compares the slot's end against the window start
            and its start against the window end. Comparing only the start
            would miss an absence that began before the window and runs into
            it — precisely the case that breaks a planning.
        """
        self.logger.debug(
            "Listing availability for hca %s between %s and %s.",
            hca_id,
            start,
            end,
        )
        statement = select(AvailabilityRow).where(AvailabilityRow.hca_id == hca_id)  # noqa: E501
        if start is not None:
            statement = statement.where(AvailabilityRow.end_date >= start)
        if end is not None:
            statement = statement.where(AvailabilityRow.start_date <= end)
        statement = statement.order_by(AvailabilityRow.start_date)
        try:
            result = await self.session.execute(statement)
            rows = result.scalars().all()
        except SQLAlchemyError as exc:
            self.logger.error("Error listing availability for hca %s: %s.", hca_id, exc)  # noqa: E501
            return []
        return [
            AvailabilitySlot(
                id=row.id,
                hca_id=row.hca_id,
                start_date=row.start_date,
                end_date=row.end_date,
                kind=row.kind,
                start_time=row.start_time,
                end_time=row.end_time,
                note=row.note,
            )
            for row in rows
        ]

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        search: Optional[str] = None,
        contract_type: Optional[ContractType] = None,
        hca_filter: Optional[HcaFilter] = None,
        hca_ids: Optional[List[str]] = None,
    ) -> List[Hca]:
        """Return a page of assistants.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            search (Optional[str]): Case-insensitive fragment matched against
                the names, the email and the city.
            contract_type (Optional[ContractType]): Restrict to one contract.
            hca_filter (Optional[HcaFilter]): The screen's filter.
            hca_ids (Optional[List[str]]): The assistants the caller may read.
                ``None`` means every assistant; an empty list means none.

        Returns:
            List[Hca]: The matching assistants, ordered by family name.
        """
        self.logger.debug(
            "Listing hcas: page=%d search=%r contract=%s.",
            page,
            search,
            contract_type.value if contract_type else None,
        )
        statement = self._build_query(
            search=search,
            contract_type=contract_type,
            hca_filter=hca_filter,
            hca_ids=hca_ids,
        )
        statement = statement.order_by(HcaRow.last_name, HcaRow.first_name)
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No hca matched the query.")
        return self.mapper.to_models(rows)

    async def list_all(self) -> List[Hca]:
        """Return every assistant.

        Returns:
            List[Hca]: Every assistant, ordered by family name.

        Notes:
            Unpaginated by design: the planning computation needs the whole
            workforce in one go, and paging through it would produce a plan
            built from a moving target.
        """
        self.logger.debug("Listing every hca for a planning run.")
        statement = select(HcaRow).order_by(HcaRow.last_name, HcaRow.first_name)  # noqa: E501
        rows = await self._fetch_all(statement)
        self.logger.info("Loaded %d hca(s) for planning.", len(rows))
        if not rows:
            self.logger.warning(
                "No hca is registered. "  # noqa: E501
                "A planning run would have nobody to assign."
            )
        return self.mapper.to_models(rows)

    async def list_by_ids(self, hca_ids: List[str]) -> List[Hca]:
        """Return the named assistants, in the planner's usual order.

        Args:
            hca_ids (List[str]): The records to load.

        Returns:
            List[Hca]: Those that exist, ordered by family name.

        Notes:
            - The workforce half of a **team-scoped** planning run. A run now
              solves over one team's field employees, and the membership rows
              are polymorphic — they carry no foreign key to ``hcas`` — so the
              identifiers come from the team and the records come from here.
            - **Ordered exactly as :meth:`list_all` is**, and that is a
              determinism requirement rather than a presentational one: the
              solver's tie-breaking follows the order it is handed the
              workforce in, so two runs over the same team must see the same
              sequence or produce different plans from identical inputs.
            - An empty argument returns an empty list without a statement. It
              means a team with nobody on it, which is a legitimate state the
              caller reports; issuing ``IN ()`` to find that out would be a
              round trip for an answer already known.
            - Identifiers naming no record are **silently absent** rather than
              an error. A membership outliving the assistant it names is
              exactly what the deletion paths guard against, and a run must not
              fail because one slipped through — the count is logged instead.
        """
        if not hca_ids:
            self.logger.warning(
                "No assistant identifier was given; this team has nobody to schedule."
            )
            return []
        self.logger.debug("Loading %d named assistant(s).", len(hca_ids))
        statement = (
            select(HcaRow)
            .where(HcaRow.id.in_(hca_ids))
            .order_by(HcaRow.last_name, HcaRow.first_name)
        )
        rows = await self._fetch_all(statement)
        if len(rows) != len(set(hca_ids)):
            self.logger.error(
                "%d assistant identifier(s) were asked for but %d record(s) "
                "exist; a membership names somebody who has been deleted.",
                len(set(hca_ids)),
                len(rows),
            )
        self.logger.info("Loaded %d assistant(s) for planning.", len(rows))
        return self.mapper.to_models(rows)

    async def count(
        self,
        search: Optional[str] = None,
        contract_type: Optional[ContractType] = None,
        hca_filter: Optional[HcaFilter] = None,
        hca_ids: Optional[List[str]] = None,
    ) -> int:
        """Return how many assistants match a query.

        Args:
            search (Optional[str]): Case-insensitive fragment.
            contract_type (Optional[ContractType]): Restrict to one contract.
            hca_filter (Optional[HcaFilter]): The screen's filter.
            hca_ids (Optional[List[str]]): The assistants the caller may read,
                so the total is narrowed exactly as the page is.

        Returns:
            int: The number of matching assistants.
        """
        return await self._count(
            self._build_query(
                search=search,
                contract_type=contract_type,
                hca_filter=hca_filter,
                hca_ids=hca_ids,
            )
        )

    async def delete(self, hca_id: str) -> bool:
        """Delete an assistant.

        Args:
            hca_id (str): The assistant to delete.

        Returns:
            bool: ``True`` when a row was deleted.

        Raises:
            SQLAlchemyError: If an account still references the assistant.
        """
        try:
            return await self._delete_row(hca_id)
        except SQLAlchemyError as exc:
            self.logger.error("Error deleting hca %s: %s.", hca_id, exc)
            raise

    async def count_for_company(self, company_id: str) -> int:
        """Return how many assistants belong to one agency.

        Args:
            company_id (str): The agency to count for.

        Returns:
            int: The number of assistants.

        Notes:
            A count rather than a list: the caller only needs to know whether
            the agency is empty, and reading every assistant to find that out
            would be a page of records fetched to be thrown away.
        """
        found = await self._count(select(HcaRow).where(HcaRow.company_id == company_id))  # noqa: E501
        self.logger.debug("Agency %s has %d assistant(s).", company_id, found)
        return found
