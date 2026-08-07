from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import Optional

# First-party imports
from models.geo.postal_address import PostalAddress
from models.people.hca_application import HcaApplication
from storage.mappers.base_mapper import BaseMapper
from storage.orm.people.hca_application_row import HcaApplicationRow


class HcaApplicationMapper(BaseMapper[HcaApplication, HcaApplicationRow]):
    """Converts between :class:`HcaApplication` and its row.

    Notes:
        The password hash crosses this boundary in both directions, as it does
        for an account: approval has to move it onto the new user, and it can
        only do that if it can read it back. Nothing about it is logged — not
        its value, not its length.

        The applicant's address carries its stored coordinate through, so an
        application listed on a review screen does not geocode itself again
        every time somebody opens the page.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=HcaApplication,
            row_class=HcaApplicationRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: HcaApplicationRow) -> HcaApplication:
        """Build an application from a row's columns.

        Args:
            row (HcaApplicationRow): The row to read.

        Returns:
            HcaApplication: The domain model.

        Raises:
            MTInvalidHcaApplicationException: If a stored value no longer
                satisfies the model's validators.
        """
        self.logger.debug(
            "Building application %s from its row (status %s).", row.id, row.status
        )
        return HcaApplication(
            id=row.id,
            company_id=row.company_id,
            first_name=row.first_name,
            last_name=row.last_name,
            phone_number=row.phone_number,
            email=row.email,
            address=PostalAddress(
                street=row.street,
                postal_code=row.postal_code,
                city=row.city,
                country=row.country,
                latitude=row.latitude,
                longitude=row.longitude,
                geocoding_error=row.geocoding_error,
            ),
            contract_type=row.contract_type,
            hashed_password=row.hashed_password,
            status=row.status,
            decided_by=row.decided_by,
            decided_at=self.timestamps.to_utc(row.decided_at),
            rejection_reason=row.rejection_reason,
            hca_id=row.hca_id,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: HcaApplicationRow, model: HcaApplication) -> None:
        """Write an application's fields onto a row's columns.

        Args:
            row (HcaApplicationRow): The row to write to.
            model (HcaApplication): The model carrying the values.
        """
        self.logger.debug(
            "Applying application for %s to its row (status %s).",
            model.email,
            model.status.value,
        )
        row.company_id = model.company_id
        row.first_name = model.first_name
        row.last_name = model.last_name
        row.phone_number = str(model.phone_number)
        row.email = str(model.email)
        row.street = model.address.street
        row.postal_code = model.address.postal_code
        row.city = model.address.city
        row.country = model.address.country
        row.latitude = model.address.latitude
        row.longitude = model.address.longitude
        row.geocoding_error = model.address.geocoding_error
        row.contract_type = model.contract_type.value if model.contract_type else None
        row.hashed_password = model.hashed_password
        row.status = model.status.value
        row.decided_by = model.decided_by
        row.decided_at = model.decided_at
        row.rejection_reason = model.rejection_reason
        row.hca_id = model.hca_id
