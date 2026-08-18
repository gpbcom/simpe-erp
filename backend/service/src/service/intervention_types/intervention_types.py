from __future__ import annotations

# Standard library imports
from decimal import Decimal
from logging import Logger, getLogger
from typing import List, Optional

# Third-party imports
from sqlalchemy.exc import IntegrityError

# First-party imports
from models.catalog.intervention_type import InterventionType
from models.schemas.requests.catalog.intervention_type_filter import (
    InterventionTypeFilter,
)
from service.certifications.certifications import CertificationTypeService
from service.certifications.exceptions import MTCertificationTypeUnknownCode
from service.skills.skills import SkillTypeService
from service.skills.exceptions import MTSkillTypeUnknownCode
from service.intervention_types.exceptions import (
    MTInterventionTypeAlreadyExists,
    MTInterventionTypeNotFound,
)
from storage.repositories.catalog.intervention_type import InterventionTypeRepository


class InterventionTypeService:
    """Manages the catalog of services the agency sells.

    Attributes:
        types (InterventionTypeRepository): The catalog store.
        certifications (Optional[CertificationTypeService]): The certification
            catalogue, consulted before a requirement is stored.
        skills (Optional[SkillTypeService]): The skill catalogue, consulted the
            same way and for the same reason.
        logger (Logger): Logger for catalog operations.

    Notes:
        Retiring a type is the only removal offered. A quote issued last year
        still names its type, so deleting the row would leave that quote
        unprintable — and its VAT rate unexplainable.
    """

    def __init__(
        self,
        types: InterventionTypeRepository,
        certifications: Optional[CertificationTypeService] = None,
        skills: Optional[SkillTypeService] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            types (InterventionTypeRepository): The catalog store.
            certifications (Optional[CertificationTypeService]): The
                certification catalogue. Optional so a caller that only reads
                the catalog need not build one. A write naming a requirement
                without it is refused rather than stored unchecked.
            skills (Optional[SkillTypeService]): The skill catalogue, optional
                on the same terms.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.types = types
        self.certifications = certifications
        self.skills = skills
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("InterventionTypeService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _assert_requirements_known(self, codes: List[str]) -> None:
        """Refuse a requirement naming a code the catalogue does not offer.

        Args:
            codes (List[str]): The certification codes being stored.

        Raises:
            MTCertificationTypeUnknownCode: If any code is unknown or retired,
                or if no certification catalogue is available to check against.

        Notes:
            **The integrity check a foreign key cannot make.** The codes live
            in a JSON array, so nothing at the database level would stop a typo
            being stored — and a requirement nobody can satisfy fails every
            planning run it touches, with a message that reads as a staffing
            problem rather than as the typo it is.

            A service built without the catalogue refuses rather than skipping
            the check. Storing a requirement unchecked is the one outcome worse
            than refusing the write.
        """
        if not codes:
            return
        if self.certifications is None:
            self.logger.error(
                "A requirement naming %d certification code(s) cannot be "
                "checked: no certification catalogue is available.",
                len(codes),
            )
            raise MTCertificationTypeUnknownCode(
                "Certification requirements cannot be verified. The "
                "certification catalogue is unavailable."
            )
        await self.certifications.assert_known(codes)

    async def _assert_skills_known(self, codes: List[str]) -> None:
        """Refuse a requirement naming a skill code the catalogue lacks.

        Args:
            codes (List[str]): The skill codes being stored.

        Raises:
            MTSkillTypeUnknownCode: If any code is unknown or retired, or if no
                skill catalogue is available to check against.

        Notes:
            The twin of :meth:`_assert_requirements_known`, and separate from
            it rather than folded in. The two catalogues answer different
            questions, and a message that named the wrong one would send
            somebody to look for a typo in the list that did not have it.
        """
        if not codes:
            return
        if self.skills is None:
            self.logger.error(
                "A requirement naming %d skill code(s) cannot be checked: no "
                "skill catalogue is available.",
                len(codes),
            )
            raise MTSkillTypeUnknownCode(
                "Skill requirements cannot be verified. The skill catalogue is "
                "unavailable."
            )
        await self.skills.assert_known(codes)

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
            MTCertificationTypeUnknownCode: If it requires a qualification the
                certification catalogue does not offer.
            MTSkillTypeUnknownCode: If it requires a skill the skill catalogue
                does not offer.
        """
        self.logger.info(
            "Adding intervention type %s to the catalog.",
            intervention_type.name,
        )
        await self._assert_requirements_known(
            intervention_type.required_certification_codes
        )
        await self._assert_skills_known(intervention_type.required_skill_codes)
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
            MTCertificationTypeUnknownCode: If it requires a qualification the
                certification catalogue does not offer.
            MTSkillTypeUnknownCode: If it requires a skill the skill catalogue
                does not offer.
        """
        self.logger.info("Updating intervention type %s.", intervention_type.id)
        await self._assert_requirements_known(
            intervention_type.required_certification_codes
        )
        await self._assert_skills_known(intervention_type.required_skill_codes)
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
        type_filter: Optional[InterventionTypeFilter] = None,
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
            page=page,
            size=size,
            include_inactive=include_inactive,
            type_filter=type_filter,
        )
        if not types:
            self.logger.warning(
                "The catalog returned nothing. No service can be quoted."
            )
        return types
