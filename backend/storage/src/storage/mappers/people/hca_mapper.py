from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, List, Optional
from uuid import uuid4

# First-party imports
from models.enums import ContractType, Weekday
from models.people.hca.availability_slot import AvailabilitySlot
from models.people.hca.certification import Certification
from models.people.hca.driving_license import DrivingLicense
from models.people.hca.skill import Skill
from models.people.hca import Hca
from storage.mappers.person_mapper import PersonMapper
from storage.orm.people.availability_row import AvailabilityRow
from storage.orm.people.certification_row import CertificationRow
from storage.orm.people.skill_row import SkillRow
from storage.orm.people.hca_row import HcaRow


class HcaMapper(PersonMapper[Hca, HcaRow]):
    """Converts between :class:`Hca` and :class:`HcaRow`.

    Attributes:
        CATEGORY_SEPARATOR (ClassVar[str]): Separator joining licence
            categories into their single stored column.
        WEEKDAY_SEPARATOR (ClassVar[str]): Separator joining the working
            weekdays into their single stored column.

    Notes:
        - Licence categories are stored as one delimited string. They are never
          queried individually — the planner only asks whether the assistant can
          drive, which is derived after the model is rebuilt — so a join table
          would buy nothing.
        - A licence is reconstructed only when at least one of its columns is
          populated. An assistant with four ``NULL`` licence columns gets
          ``driving_license = None``, which is what makes "no licence" and
          "empty licence" the same thing on the way back up.
        - This is the only mapper here with children. They are written through
          the same :meth:`_apply_fields` on create and on update, which is what
          guarantees an inserted assistant and an edited one end up with their
          certifications, skills and absences stored identically.
        - A skill keeps the identifier it arrives with, where a certification
          is always given a fresh one. A skill is addressed by identifier from
          the moment it is stored — its owner or a manager deletes it by naming
          it — so regenerating one on every write would break every link a
          client is holding, and turn an edit elsewhere on the record into a
          silent renumbering.
    """

    CATEGORY_SEPARATOR: ClassVar[str] = ","
    WEEKDAY_SEPARATOR: ClassVar[str] = ","

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=Hca, row_class=HcaRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _license_to_model(self, row: HcaRow) -> Optional[DrivingLicense]:
        """Rebuild the driving licence from its flattened columns.

        Args:
            row (HcaRow): The row to read.

        Returns:
            Optional[DrivingLicense]: The licence, or ``None`` when every
            licence column is unset.

        Raises:
            MTInvalidDrivingLicenseException: If a stored licence value no
                longer satisfies the licence validators.
        """
        has_license = any(
            (
                row.driving_license_categories,
                row.driving_license_number,
                row.driving_license_obtained_on,
                row.driving_license_expires_on,
            )
        )
        if not has_license:
            self.logger.debug("Hca row %s holds no driving licence.", row.id)
            return None
        raw_categories = row.driving_license_categories or ""
        categories = [
            category
            for category in raw_categories.split(self.CATEGORY_SEPARATOR)
            if category
        ]
        if not categories:
            self.logger.warning(
                "Hca row %s has licence columns but no category: the planner "
                "will not treat them as able to drive.",
                row.id,
            )
        self.logger.debug(
            "Rebuilding the driving licence of hca row %s (%d category/ies).",
            row.id,
            len(categories),
        )
        return DrivingLicense(
            categories=categories,
            number=row.driving_license_number,
            obtained_on=row.driving_license_obtained_on,
            expires_on=row.driving_license_expires_on,
        )

    def _apply_license(
        self, row: HcaRow, license_model: Optional[DrivingLicense]
    ) -> None:
        """Flatten a driving licence onto a row's licence columns.

        Args:
            row (HcaRow): The row to write to.
            license_model (Optional[DrivingLicense]): The licence, or ``None``
                to clear every licence column.

        Notes:
            Clearing all four columns on ``None`` matters on update: an
            assistant whose licence is removed must not keep the old number.
        """
        if license_model is None:
            self.logger.debug("Clearing the licence columns of hca row %s.", row.id)  # noqa: E501
            row.driving_license_categories = None
            row.driving_license_number = None
            row.driving_license_obtained_on = None
            row.driving_license_expires_on = None
            return
        self.logger.debug(
            "Storing the driving licence of hca row %s (%d category/ies).",
            row.id,
            len(license_model.categories),
        )
        row.driving_license_categories = self.CATEGORY_SEPARATOR.join(
            license_model.categories
        )
        row.driving_license_number = license_model.number
        row.driving_license_obtained_on = license_model.obtained_on
        row.driving_license_expires_on = license_model.expires_on

    def _certifications_to_model(self, row: HcaRow) -> List[Certification]:
        """Rebuild the qualifications held by an assistant.

        Args:
            row (HcaRow): The row to read, with its children loaded.

        Returns:
            List[Certification]: The qualifications.

        Raises:
            MTInvalidCertificationException: If a stored qualification value no
                longer satisfies the certification validators.
        """
        self.logger.debug(
            "Rebuilding %d certification(s) of hca row %s.",
            len(row.certifications),
            row.id,
        )
        return [
            Certification(
                name=certification.name,
                code=certification.code,
                issuer=certification.issuer,
                obtained_on=certification.obtained_on,
                expires_on=certification.expires_on,
            )
            for certification in row.certifications
        ]

    def _skills_to_model(self, row: HcaRow) -> List[Skill]:
        """Rebuild the skills an assistant declared.

        Args:
            row (HcaRow): The row to read, with its children loaded.

        Returns:
            List[Skill]: The declared skills.

        Raises:
            MTInvalidSkillException: If a stored skill value no longer
                satisfies the skill validators.
        """
        self.logger.debug(
            "Rebuilding %d skill(s) of hca row %s.",
            len(row.skills),
            row.id,
        )
        return [
            Skill(
                id=skill.id,
                name=skill.name,
                code=skill.code,
                issuer=skill.issuer,
                obtained_on=skill.obtained_on,
                expires_on=skill.expires_on,
            )
            for skill in row.skills
        ]

    def _availability_to_model(self, row: HcaRow) -> List[AvailabilitySlot]:
        """Rebuild the absences declared by an assistant.

        Args:
            row (HcaRow): The row to read, with its children loaded.

        Returns:
            List[AvailabilitySlot]: The absences.

        Raises:
            MTInvalidAvailabilitySlotException: If a stored absence value no
                longer satisfies the slot validators.
        """
        self.logger.debug(
            "Rebuilding %d availability slot(s) of hca row %s.",
            len(row.availability),
            row.id,
        )
        return [
            AvailabilitySlot(
                id=slot.id,
                hca_id=slot.hca_id,
                start_date=slot.start_date,
                end_date=slot.end_date,
                kind=slot.kind,
                start_time=slot.start_time,
                end_time=slot.end_time,
                note=slot.note,
            )
            for slot in row.availability
        ]

    def _weekdays_to_model(self, row: HcaRow) -> List[Weekday]:  # noqa: E501
        """Rebuild the working week an assistant declared.

        Args:
            row (HcaRow): The row to read.

        Returns:
            List[Weekday]: The days worked, ordered Monday first.

        Raises:
            MTHcaInvalidWorkingWeekdays: If a stored value is not a known
                weekday.

        Notes:
            A blank column falls back to the model's default working week
            rather than to "no days". The column is ``NOT NULL``, so blank can
            only come from a row written before the migration backfilled it —
            and reading that as "works nothing" would quietly empty the
            workforce, which is the failure mode that looks like success.
        """
        raw = (row.working_weekdays or "").strip()
        if not raw:
            self.logger.warning(
                "Hca row %s has no working week stored; defaulting to the "
                "standard week.",
                row.id,
            )
            return list(Hca.DEFAULT_WORKING_WEEKDAYS)
        self.logger.debug("Rebuilding the working week of hca row %s.", row.id)
        return [
            Weekday(value.strip())
            for value in raw.split(self.WEEKDAY_SEPARATOR)
            if value.strip()
        ]

    def _certification_rows(
        self, hca_id: str, certifications: List[Certification]
    ) -> List[CertificationRow]:
        """Build the certification rows for an assistant.

        Args:
            hca_id (str): The owning assistant's identifier.
            certifications (List[Certification]): The qualifications to store.

        Returns:
            List[CertificationRow]: Freshly built rows.
        """
        self.logger.debug(
            "Building %d certification row(s) for hca %s.",
            len(certifications),
            hca_id,
        )
        return [
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

    def _skill_rows(self, hca_id: str, skills: List[Skill]) -> List[SkillRow]:
        """Build the skill rows for an assistant.

        Args:
            hca_id (str): The owning assistant's identifier.
            skills (List[Skill]): The skills to store.

        Returns:
            List[SkillRow]: Freshly built rows, keeping each stored skill's own
            identifier and minting one for a skill that has none yet.

        Notes:
            The identifier is preserved rather than regenerated, unlike
            :meth:`_certification_rows`. A client holds these identifiers so it
            can delete one, and a rewrite that renumbered them would turn a
            perfectly ordinary edit — changing a telephone number — into a
            silent invalidation of every delete link on the screen.
        """
        self.logger.debug(
            "Building %d skill row(s) for hca %s.",
            len(skills),
            hca_id,
        )
        return [
            SkillRow(
                id=skill.id if skill.id else str(uuid4()),
                hca_id=hca_id,
                name=skill.name,
                code=skill.code,
                issuer=skill.issuer,
                obtained_on=skill.obtained_on,
                expires_on=skill.expires_on,
            )
            for skill in skills
        ]

    def _availability_rows(
        self, hca_id: str, availability: List[AvailabilitySlot]
    ) -> List[AvailabilityRow]:
        """Build the availability rows for an assistant.

        Args:
            hca_id (str): The owning assistant's identifier.
            availability (List[AvailabilitySlot]): The absences to store.

        Returns:
            List[AvailabilityRow]: Freshly built rows.

        Notes:
            The slot's own ``hca_id`` is ignored in favour of the owning row's:
            a payload that names another assistant must not be able to file an
            absence against them. It is logged at ``WARNING`` rather than
            rejected, because the honest case — a client echoing back a slot it
            read elsewhere — is a bug in the caller, not an attack, and the
            absence still belongs to the assistant being written.
        """
        self.logger.debug(
            "Building %d availability row(s) for hca %s.",
            len(availability),
            hca_id,
        )
        for slot in availability:
            if slot.hca_id and slot.hca_id != hca_id:
                self.logger.warning(
                    "Availability slot %s names hca %s: filing it against "
                    "hca %s instead.",
                    slot.id,
                    slot.hca_id,
                    hca_id,
                )
        return [
            AvailabilityRow(
                id=slot.id if slot.id else str(uuid4()),
                hca_id=hca_id,
                start_date=slot.start_date,
                end_date=slot.end_date,
                kind=slot.kind.value,
                start_time=slot.start_time,
                end_time=slot.end_time,
                note=slot.note,
            )
            for slot in availability
        ]

    def _build_model(self, row: HcaRow) -> Hca:
        """Build an assistant from a row's columns and children.

        Args:
            row (HcaRow): The row to read, with its children loaded.

        Returns:
            Hca: The domain model.

        Raises:
            MTInvalidHcaException: If a stored value no longer satisfies the
                model's validators.
        """
        self.logger.debug(
            "Building an hca from row %s (contract %s).",
            row.id,
            row.contract_type,
        )
        return Hca(
            id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            phone_number=row.phone_number,
            email=row.email,
            address=self._address_to_model(row),
            company_id=row.company_id,
            contract_type=row.contract_type,
            certifications=self._certifications_to_model(row),
            skills=self._skills_to_model(row),
            driving_license=self._license_to_model(row),
            photo_url=row.photo_url,
            availability=self._availability_to_model(row),
            working_weekdays=self._weekdays_to_model(row),
            field_employee=row.field_employee,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: HcaRow, model: Hca) -> None:
        """Write an assistant's fields and children onto a row.

        Args:
            row (HcaRow): The row to write to, carrying its identifier.
            model (Hca): The model carrying the values.

        Notes:
            The children are replaced wholesale rather than diffed. The
            relationships are configured ``delete-orphan``, so assigning a new
            list deletes the rows that dropped out — which is the behaviour an
            edit form expects, and far simpler to reason about than a merge.
        """
        self._apply_person_fields(row, model)
        row.company_id = model.company_id
        row.contract_type = ContractType(model.contract_type).value
        row.photo_url = str(model.photo_url) if model.photo_url else None
        row.working_weekdays = self.weekdays_to_column(model.working_weekdays)
        row.field_employee = model.field_employee
        self._apply_license(row, model.driving_license)
        row.certifications = self._certification_rows(row.id, model.certifications)
        row.skills = self._skill_rows(row.id, model.skills)
        row.availability = self._availability_rows(row.id, model.availability)
        self.logger.info(
            "Stored hca row %s with %d certification(s), %d skill(s) and "
            "%d absence(s).",
            row.id,
            len(row.certifications),
            len(row.skills),
            len(row.availability),
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def weekdays_to_column(self, working_weekdays: List[Weekday]) -> str:  # noqa: E501
        """Render a working week into its single stored column.

        Args:
            working_weekdays (List[Weekday]): The days worked.

        Returns:
            str: The days, comma-separated and ordered Monday first.

        Notes:
            Sorted on the way out as well as on the way in. The model already
            orders the list, but this is the last point before the value
            becomes a string that two equal weeks must compare equal as.
        """
        ordered = sorted(set(working_weekdays), key=lambda day: day.iso_weekday())  # noqa: E501
        self.logger.debug("Storing a working week of %d day(s).", len(ordered))
        return self.WEEKDAY_SEPARATOR.join(day.value for day in ordered)
