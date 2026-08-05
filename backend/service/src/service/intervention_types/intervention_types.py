from __future__ import annotations

# Standard library imports
from decimal import Decimal
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy.exc import IntegrityError

# First-party imports
from models.catalog.intervention_type import InterventionType
from service.intervention_types.exceptions import (
    MTInterventionTypeAlreadyExists,
    MTInterventionTypeNotFound,
)
from storage.repositories.intervention_type import InterventionTypeRepository


class InterventionTypeService:
    """Manages the catalog of services the agency sells.

    Attributes:
        types (InterventionTypeRepository): The catalog store.
        logger (Logger): Logger for catalog operations.

    Notes:
        Retiring a type is the only removal offered. A quote issued last year
        still names its type, so deleting the row would leave that quote
        unprintable — and its VAT rate unexplainable.
    """

    def __init__(
        self,
        types: InterventionTypeRepository,
        logger: Optional[Logger] = None,  # noqa: E501
    ) -> None:
        """Initialize the service.

        Args:
            types (InterventionTypeRepository): The catalog store.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.types = types
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("InterventionTypeService created.")

    #############################
    # Publicly Exposed Mzethods #
    #############################

    async def create(self, intervention_type: InterventionType) -> InterventionType:  # noqa: E501
        """Add a type to the catalog.

        Args:
            intervention_type (InterventionType): The type to add.

        Returns:
            InterventionType: The stored type.

        Raises:
            MTInterventionTypeAlreadyExists: If the name or the code is taken.
        """
        self.logger.info(
            "Adding intervention type %s to the catalog.",
            intervention_type.name,  # noqa: E501
        )
        try:
            return await self.types.create(intervention_type)
        except IntegrityError as exc:
            self.logger.warning(
                "Refused to add %s: its name or code is already used.",
                intervention_type.name,
            )
            raise MTInterventionTypeAlreadyExists(
                f"An intervention type already uses the name "
                f"{intervention_type.name!r} or the code "
                f"{intervention_type.code!r}."
            ) from exc

    async def get(self, type_id: str) -> InterventionType:
        """Return a type by identifier.

        Args:
            type_id (str): The identifier to look up.

        Returns:
            InterventionType: The type.

        Raises:
            MTInterventionTypeNotFound: If no such type exists.
        """
        found = await self.types.get(type_id)
        if found is None:
            self.logger.warning("Intervention type %s does not exist.", type_id)
            raise MTInterventionTypeNotFound(
                f"No intervention type {type_id!r} exists."
            )
        return found

    async def update(self, intervention_type: InterventionType) -> InterventionType:  # noqa: E501
        """Update a type in the catalog.

        Args:
            intervention_type (InterventionType): The type to store.

        Returns:
            InterventionType: The updated type.

        Raises:
            MTInterventionTypeNotFound: If no such type exists.
            MTInterventionTypeAlreadyExists: If the new name or code is taken.
        """
        self.logger.info("Updating intervention type %s.", intervention_type.id)
        try:
            updated = await self.types.update(intervention_type)
        except IntegrityError as exc:
            raise MTInterventionTypeAlreadyExists(
                f"Another intervention type already uses the name "
                f"{intervention_type.name!r} or the code "
                f"{intervention_type.code!r}."
            ) from exc
        if updated is None:
            raise MTInterventionTypeNotFound(
                f"No intervention type {intervention_type.id!r} exists."
            )
        return updated

    async def set_rate(
        self, type_id: str, base_hourly_rate_ht: Optional[Decimal]
    ) -> InterventionType:
        """Reprice a type.

        Args:
            type_id (str): The type to reprice.
            base_hourly_rate_ht (Optional[Decimal]): The new rate, or ``None``
                to bill the agency default.

        Returns:
            InterventionType: The updated type.

        Raises:
            MTInterventionTypeNotFound: If no such type exists.

        Notes:
            Repricing never touches an issued quote. A quote line stores the
            amounts computed when it was priced, not a reference to this rate,
            so a customer is never re-billed for work already quoted.
        """
        updated = await self.types.set_rate(type_id, base_hourly_rate_ht)
        if updated is None:
            raise MTInterventionTypeNotFound(
                f"No intervention type {type_id!r} exists."
            )
        self.logger.info(
            "Intervention type %s now bills %s.",
            type_id,
            base_hourly_rate_ht if base_hourly_rate_ht else "the agency default",
        )
        return updated

    async def retire(self, type_id: str) -> InterventionType:
        """Take a type out of the sellable catalog.

        Args:
            type_id (str): The type to retire.

        Returns:
            InterventionType: The retired type.

        Raises:
            MTInterventionTypeNotFound: If no such type exists.
        """
        updated = await self.types.set_active(type_id, False)
        if updated is None:
            raise MTInterventionTypeNotFound(
                f"No intervention type {type_id!r} exists."
            )
        self.logger.info("Retired intervention type %s.", type_id)
        return updated

    async def restore(self, type_id: str) -> InterventionType:
        """Put a retired type back in the sellable catalog.

        Args:
            type_id (str): The type to restore.

        Returns:
            InterventionType: The restored type.

        Raises:
            MTInterventionTypeNotFound: If no such type exists.
        """
        updated = await self.types.set_active(type_id, True)
        if updated is None:
            raise MTInterventionTypeNotFound(
                f"No intervention type {type_id!r} exists."
            )
        self.logger.info("Restored intervention type %s.", type_id)
        return updated

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        include_inactive: bool = False,
    ) -> List[InterventionType]:
        """Return a page of the catalog.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            include_inactive (bool): Whether retired types are included.

        Returns:
            List[InterventionType]: The matching types.
        """
        self.logger.debug(
            "Listing the catalog: page=%d include_inactive=%s.",
            page,
            include_inactive,
        )
        types = await self.types.list(
            page=page, size=size, include_inactive=include_inactive
        )
        if not types:
            self.logger.warning(
                "The catalog returned nothing; no service can be quoted."
            )
        return types
