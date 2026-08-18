from __future__ import annotations

# Standard library imports
from abc import ABC

# First-party imports
from models.geo.postal_address import PostalAddress
from storage.mappers.base_mapper import BaseMapper, ModelType, RowType


class PersonMapper(BaseMapper[ModelType, RowType], ABC):
    """Shared mapping for the tables that describe a person.

    Notes:
        - Customers and assistants are stored differently in almost every
          respect, but they carry the same identity block: a name, a way to
          reach them, and an address. That block is flattened onto columns
          identically on both tables, and rebuilding it in two places is how a
          geocoding column ends up written on one table and not the other.
        - The address is flattened into columns rather than stored as a JSON
          blob, which is why it needs mapping at all: the planner filters on the
          city and reads the coordinates on every solve.
        - A licence, a contract or a registration status is *not* handled here.
          Only what both tables genuinely share belongs at this level. The rest
          stays in the mapper that owns it.
    """

    ############################
    # Internal Helpers Methods #
    ############################

    def _address_to_model(self, row: RowType) -> PostalAddress:
        """Rebuild the postal address from its flattened columns.

        Args:
            row (RowType): The row to read.

        Returns:
            PostalAddress: The address, including its geocoding outcome.

        Raises:
            MTInvalidPostalAddressException: If a stored address value no
                longer satisfies the address validators.

        Notes:
            Reading a row does not geocode. Every stored address carries either
            a coordinate or a ``geocoding_error``, and
            :class:`~models.geo.postal_address.PostalAddress` treats both as
            already resolved — so rebuilding a page of rows issues no network
            request, without this layer having to suppress anything.
        """
        self.logger.debug(
            "Rebuilding the address of %s row %s.",
            self.row_class.__tablename__,
            row.id,
        )
        if row.latitude is None or row.longitude is None:
            self.logger.debug(
                "%s row %s carries no coordinates (geocoding error: %s).",
                self.row_class.__tablename__,
                row.id,
                row.geocoding_error,
            )
        return PostalAddress(
            street=row.street,
            postal_code=row.postal_code,
            city=row.city,
            country=row.country,
            latitude=row.latitude,
            longitude=row.longitude,
            geocoding_error=row.geocoding_error,
        )

    def _apply_person_fields(self, row: RowType, model: ModelType) -> None:
        """Write the shared identity and address fields onto a row.

        Args:
            row (RowType): The row to write to.
            model (ModelType): The model carrying the values.

        Notes:
            The phone number and the email address are stored as plain strings.
            Both are rich types on the model — the number has already been
            normalized to its international form by the validator — and writing
            them straight through would hand SQLAlchemy an object it cannot
            bind.
        """
        self.logger.debug(
            "Applying the identity fields of %s onto %s row %s.",
            self.model_class.__name__,
            self.row_class.__tablename__,
            row.id,
        )
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
        if model.address.geocoding_error:
            self.logger.warning(
                "Storing %s row %s with a geocoding error (%s): it cannot be "
                "routed to until the address resolves.",
                self.row_class.__tablename__,
                row.id,
                model.address.geocoding_error,
            )
