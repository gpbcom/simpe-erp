from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import Optional

# First-party imports
from models.companies.company import Company
from models.geo.postal_address import PostalAddress
from storage.mappers.base_mapper import BaseMapper
from storage.orm.companies.company_row import CompanyRow


class CompanyMapper(BaseMapper[Company, CompanyRow]):
    """Converts between :class:`Company` and :class:`CompanyRow`.

    Notes:
        The address is optional on a company, unlike on a person, so it is
        rebuilt only when a street was stored. Building an empty
        :class:`~models.geo.postal_address.PostalAddress` instead would send a
        blank address to Nominatim on every read.

        A stored address is handed both its coordinate and, where it failed,
        the recorded error. That combination is what marks it resolved, so
        re-reading a company never calls the geocoder again.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=Company, row_class=CompanyRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_address(self, row: CompanyRow) -> Optional[PostalAddress]:
        """Rebuild the registered office, if one was stored.

        Args:
            row (CompanyRow): The row to read.

        Returns:
            Optional[PostalAddress]: The office, or ``None``.
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

    def _build_model(self, row: CompanyRow) -> Company:
        """Build a company from a row's columns.

        Args:
            row (CompanyRow): The row to read.

        Returns:
            Company: The domain model.

        Raises:
            MTInvalidCompanyException: If a stored value no longer satisfies
                the model's validators.
        """
        self.logger.debug("Building company %s from its row.", row.id)
        return Company(
            id=row.id,
            name=row.name,
            registration_number=row.registration_number,
            contact_email=row.contact_email,
            legal_form=row.legal_form,
            share_capital=row.share_capital,
            rcs_number=row.rcs_number,
            vat_number=row.vat_number,
            phone_number=row.phone_number,
            iban=row.iban,
            bic=row.bic,
            logo_url=row.logo_url,
            address=self._build_address(row),
            is_accepting_applications=row.is_accepting_applications,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: CompanyRow, model: Company) -> None:
        """Write a company's fields onto a row's columns.

        Args:
            row (CompanyRow): The row to write to.
            model (Company): The model carrying the values.
        """
        self.logger.debug("Applying company %s to its row.", model.name)
        row.name = model.name
        row.registration_number = model.registration_number
        row.contact_email = str(model.contact_email) if model.contact_email else None
        row.legal_form = model.legal_form
        row.share_capital = model.share_capital
        row.rcs_number = model.rcs_number
        row.vat_number = model.vat_number
        row.phone_number = model.phone_number
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
