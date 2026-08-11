from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import Optional

# First-party imports
from models.enums import RegistrationStatus
from models.people.customer import Customer
from storage.mappers.person_mapper import PersonMapper
from storage.orm.people.customer_row import CustomerRow


class CustomerMapper(PersonMapper[Customer, CustomerRow]):
    """Converts between :class:`Customer` and :class:`CustomerRow`.

    Notes:
        - The mapper is what keeps the layering rule honest: the ORM row never
          leaves ``storage``, and the domain model never carries a SQLAlchemy
          type. Every repository read ends here, and every write starts here.
        - The identity block and the address are mapped by
          :class:`~storage.mappers.person_mapper.PersonMapper`; a customer adds
          only its registration status on top of them.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=Customer, row_class=CustomerRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: CustomerRow) -> Customer:
        """Build a customer from a row's columns.

        Args:
            row (CustomerRow): The row to read.

        Returns:
            Customer: The domain model.

        Raises:
            MTInvalidCustomerException: If a stored value no longer satisfies
                the model's validators.
            MTInvalidPostalAddressException: If a stored address value no
                longer satisfies the address validators.
        """
        self.logger.debug(
            "Building a customer from row %s (status %s).",
            row.id,
            row.registration_status,
        )
        return Customer(
            id=row.id,
            first_name=row.first_name,
            last_name=row.last_name,
            phone_number=row.phone_number,
            email=row.email,
            address=self._address_to_model(row),
            registration_status=row.registration_status,
            billing_periodicity=row.billing_periodicity,
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: CustomerRow, model: Customer) -> None:
        """Write a customer's fields onto a row.

        Args:
            row (CustomerRow): The row to write to.
            model (Customer): The model carrying the values.

        Notes:
            - The status is round-tripped through
              :class:`~models.enums.RegistrationStatus` rather than read straight
              off the model, so the column can only ever hold a value the enum
              recognises — the repository filters on it, and a status nobody
              queries for is a customer who quietly disappears from every list.
            - The billing periodicity is written as ``None`` when the customer
              has no override, never as the agency's current rule. Writing the
              resolved value would turn "follows the agency" into a frozen copy
              of what the agency happened to bill on the day the record was
              saved, and the customer would silently stop tracking the setting.
        """
        self._apply_person_fields(row, model)
        status = RegistrationStatus(model.registration_status)
        self.logger.debug(
            "Applying registration status %s onto customer row %s.",
            status.value,
            row.id,
        )
        if status is RegistrationStatus.STOPPED:
            self.logger.info(
                "Customer row %s is stored as stopped: no new intervention "
                "will be planned for them.",
                row.id,
            )
        row.registration_status = status.value
        periodicity = model.billing_periodicity
        if periodicity is not None:
            self.logger.info(
                "Customer row %s is billed %s, not on the agency's own rule.",
                row.id,
                periodicity.value,
            )
        row.billing_periodicity = periodicity.value if periodicity else None
