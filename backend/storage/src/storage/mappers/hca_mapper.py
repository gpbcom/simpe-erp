from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import ClassVar, List, Optional
from uuid import uuid4

# First-party imports
from models.enums import ContractType
from models.people.availability_slot import AvailabilitySlot
from models.people.certification import Certification
from models.people.driving_license import DrivingLicense
from models.people.hca import Hca
from storage.mappers.person_mapper import PersonMapper
from storage.orm.availability_row import AvailabilityRow
from storage.orm.certification_row import CertificationRow
from storage.orm.hca_row import HcaRow


class HcaMapper(PersonMapper[Hca, HcaRow]):
    """Converts between :class:`Hca` and :class:`HcaRow`.

    Attributes:
        CATEGORY_SEPARATOR (ClassVar[str]): Separator joining licence
            categories into their single stored column.

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
          certifications and absences stored identically.
    """

    CATEGORY_SEPARATOR: ClassVar[str] = ","

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
            self.logger.debug("Clearing the licence columns of hca row %s.", row.id)
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
                issuer=certification.issuer,
                obtained_on=certification.obtained_on,
                expires_on=certification.expires_on,
            )
            for certification in row.certifications
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
                issuer=certification.issuer,
                obtained_on=certification.obtained_on,
                expires_on=certification.expires_on,
            )
            for certification in certifications
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
            driving_license=self._license_to_model(row),
            photo_url=row.photo_url,
            availability=self._availability_to_model(row),
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
        self._apply_license(row, model.driving_license)
        row.certifications = self._certification_rows(row.id, model.certifications)
        row.availability = self._availability_rows(row.id, model.availability)
        self.logger.info(
            "Stored hca row %s with %d certification(s) and %d absence(s).",
            row.id,
            len(row.certifications),
            len(row.availability),
        )
