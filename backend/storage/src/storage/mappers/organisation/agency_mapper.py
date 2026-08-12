from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import List, Optional, Sequence
from uuid import uuid4

# First-party imports
from models.geo.postal_address import PostalAddress
from models.organisation.agency.agency import Agency
from models.organisation.agency.agency_member import AgencyMember
from storage.mappers.base_mapper import BaseMapper
from storage.orm.organisation.agency_member_row import AgencyMemberRow
from storage.orm.organisation.agency_row import AgencyRow


class AgencyMapper(BaseMapper[Agency, AgencyRow]):
    """Converts between :class:`Agency` and :class:`AgencyRow`.

    Notes:
        - The address is optional on a site, as it is on a company, so it is
          rebuilt only when a street was stored. Building an empty
          :class:`~models.geo.postal_address.PostalAddress` instead would send a
          blank address to Nominatim on every read — and this row is read on
          every quote written, because the attribution rule measures from it.
        - A stored address is handed both its coordinate and, where it failed,
          the recorded error. That combination is what marks it resolved, so
          re-reading a site never calls the geocoder again.
        - The membership rows are converted **here** rather than by a mapper of
          their own, the way
          :class:`~storage.mappers.people.hca_mapper.HcaMapper` converts a
          certification. A membership carries no identifier of its own, so it
          cannot satisfy the contract :class:`BaseMapper` rests on — and a
          second mapper class for two columns would be a file to keep in step
          for no gain.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=Agency, row_class=AgencyRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_address(self, row: AgencyRow) -> Optional[PostalAddress]:
        """Rebuild the site's address, if one was stored.

        Args:
            row (AgencyRow): The row to read.

        Returns:
            Optional[PostalAddress]: The address, or ``None``.
        """
        if not row.street:
            return None
        return PostalAddress(
            street=row.street,
            postal_code=row.postal_code,
            city=row.city,
            country=row.country,
            latitude=row.latitude,
            longitude=row.longitude,
            geocoding_error=row.geocoding_error,
        )

    def _build_model(self, row: AgencyRow) -> Agency:
        """Build a site from a row's columns.

        Args:
            row (AgencyRow): The row to read.

        Returns:
            Agency: The domain model.

        Raises:
            MTInvalidAgencyException: If a stored value no longer satisfies the
                model's validators.
        """
        self.logger.debug("Building agency %s from its row.", row.id)
        return Agency(
            id=row.id,
            company_id=row.company_id,
            name=row.name,
            agency_type=row.agency_type,
            legal_form=row.legal_form,
            share_capital=row.share_capital,
            rcs_number=row.rcs_number,
            vat_number=row.vat_number,
            sap_declaration_number=row.sap_declaration_number,
            phone_number=row.phone_number,
            registration_number=row.registration_number,
            contact_email=row.contact_email,
            iban=row.iban,
            bic=row.bic,
            logo_url=row.logo_url,
            is_accepting_applications=row.is_accepting_applications,
            address=self._build_address(row),
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: AgencyRow, model: Agency) -> None:
        """Write a site's fields onto a row's columns.

        Args:
            row (AgencyRow): The row to write to.
            model (Agency): The model carrying the values.
        """
        self.logger.debug("Applying agency %s to its row.", model.name)
        row.company_id = model.company_id
        row.name = model.name
        row.agency_type = model.agency_type.value
        row.legal_form = model.legal_form
        row.share_capital = model.share_capital
        row.rcs_number = model.rcs_number
        row.vat_number = model.vat_number
        row.sap_declaration_number = model.sap_declaration_number
        row.phone_number = model.phone_number
        row.registration_number = model.registration_number
        row.contact_email = str(model.contact_email) if model.contact_email else None
        row.iban = model.iban
        row.bic = model.bic
        row.logo_url = model.logo_url
        row.is_accepting_applications = model.is_accepting_applications
        address = model.address
        row.street = address.street if address else None
        row.postal_code = address.postal_code if address else None
        row.city = address.city if address else None
        row.country = address.country if address else None
        row.latitude = address.latitude if address else None
        row.longitude = address.longitude if address else None
        row.geocoding_error = address.geocoding_error if address else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_member(self, row: AgencyMemberRow) -> AgencyMember:
        """Convert a membership row into its model.

        Args:
            row (AgencyMemberRow): The row to read.

        Returns:
            AgencyMember: The membership.

        Raises:
            MTInvalidAgencyException: If the stored kind is not a known one.
        """
        self.logger.debug("Building agency membership %s from its row.", row.id)
        return AgencyMember(member_kind=row.member_kind, member_id=row.member_id)

    def to_members(self, rows: Sequence[AgencyMemberRow]) -> List[AgencyMember]:
        """Convert several membership rows into their models.

        Args:
            rows (Sequence[AgencyMemberRow]): The rows to read.

        Returns:
            List[AgencyMember]: The memberships, in the order given.
        """
        self.logger.debug("Building %d agency membership(s) from rows.", len(rows))
        return [self.to_member(row) for row in rows]

    def to_member_row(self, agency_id: str, member: AgencyMember) -> AgencyMemberRow:
        """Build a fresh membership row.

        Args:
            agency_id (str): The site the person joins.
            member (AgencyMember): Which person, and which kind of record.

        Returns:
            AgencyMemberRow: A row ready to be added to a session.

        Notes:
            The site is a **parameter**, not something read off the membership.
            The model deliberately carries no ``agency_id``, so the owning site
            can only come from the route the caller reached — which is what
            stops a payload filing somebody into a site it was not sent to.
        """
        self.logger.debug(
            "Building an agency membership row for %s %s at site %s.",
            member.member_kind.value,
            member.member_id,
            agency_id,
        )
        return AgencyMemberRow(
            id=str(uuid4()),
            agency_id=agency_id,
            member_kind=member.member_kind.value,
            member_id=member.member_id,
            created_at=self._utc_now(),
        )
