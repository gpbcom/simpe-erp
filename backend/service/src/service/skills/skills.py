from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Sequence, Set

# Third-party imports
from sqlalchemy.exc import IntegrityError

# First-party imports
from models.catalog.skill_type import SkillType
from models.schemas.requests.catalog.skill_type_filter import SkillTypeFilter
from service.skills.exceptions import (
    MTSkillTypeAlreadyExists,
    MTSkillTypeInUse,
    MTSkillTypeNotFound,
    MTSkillTypeUnknownCode,
)

# isort: off
from storage.repositories.catalog.skill_type import SkillTypeRepository
from storage.repositories.catalog.intervention_type import InterventionTypeRepository  # noqa: E501

# isort: on
from storage.repositories.people.hca import HcaRepository


class SkillTypeService:
    """Manages the catalogue of skills the agency recognises.

    Attributes:
        skills (SkillTypeRepository): The catalogue store.
        hcas (HcaRepository): The workforce, consulted before a delete.
        types (InterventionTypeRepository): The service catalogue, consulted
            before a delete.
        logger (Logger): Logger for catalogue operations.

    Notes:
        - **This service owns the referential integrity the database does
          not.** A required skill is a JSON array on ``intervention_types`` and
          an optional string on ``skills``, and a foreign key can constrain
          neither the first nor, usefully, the second. :meth:`assert_known` is
          what every writer of a requirement calls, and :meth:`delete` is what
          refuses to strand one.
        - Retiring is the ordinary way to take a skill out of use. Deleting is
          offered only while nothing refers to the entry, which in practice
          means the morning it was added by mistake.
        - The twin of
          :class:`~service.certifications.certifications.CertificationTypeService`,
          and a separate class rather than one parameterised by which catalogue
          it manages. The two differ in who may write the *other* side — a
          manager records a certification, an assistant declares a skill — and a
          shared service would have had to be told which it was on every call,
          which is a permission decided by an argument.
    """

    def __init__(
        self,
        skills: SkillTypeRepository,
        hcas: HcaRepository,
        types: InterventionTypeRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            skills (SkillTypeRepository): The catalogue store.
            hcas (HcaRepository): The workforce, consulted before a delete.
            types (InterventionTypeRepository): The service catalogue,
                consulted before a delete.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.skills = skills
        self.hcas = hcas
        self.types = types
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("SkillTypeService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _holders_of(self, code: str) -> List[str]:
        """Return the assistants who have declared a skill.

        Args:
            code (str): The catalogue code to look for.

        Returns:
            List[str]: The full names of the assistants who declared it.

        Notes:
            Names rather than identifiers, because the answer ends up in a
            refusal message a manager reads. "Declared by Luc Martin and 2
            others" tells them where to go; three UUIDs do not.
        """
        workforce = await self.hcas.list_all()
        return [
            assistant.full_name()
            for assistant in workforce
            if any(declared.code == code for declared in assistant.skills)
        ]

    async def _services_requiring(self, code: str) -> List[str]:
        """Return the catalogue entries that require a skill.

        Args:
            code (str): The catalogue code to look for.

        Returns:
            List[str]: The names of the services requiring it.
        """
        services = await self.types.list(
            size=self.types.MAX_PAGE_SIZE, include_inactive=True
        )
        return [
            service.name for service in services if code in service.required_skill_codes
        ]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def assert_known(self, codes: Sequence[str]) -> None:
        """Refuse a requirement naming a code the catalogue does not offer.

        Args:
            codes (Sequence[str]): The codes a service or a quote line
                requires.

        Raises:
            MTSkillTypeUnknownCode: If any code is unknown or retired.

        Notes:
            - **This is the referential integrity the JSON column cannot have.**
              A foreign key cannot reach inside an array, so the check runs here
              instead — and it produces a better message than a constraint
              would: it names the offending code and lists what the catalogue
              does offer, which is what somebody who has just made a typo needs.
            - Retired entries are refused as well as unknown ones. Retiring is
              how a skill stops being asked for; letting a new requirement name
              one would quietly undo that.
            - One query for every code, not one per code — see
              :meth:`~storage.repositories.catalog.skill_type.SkillTypeRepository.known_codes`.
        """
        if not codes:
            self.logger.debug("No skill requirement to check.")
            return
        wanted = {code.strip().upper() for code in codes}
        known: Set[str] = await self.skills.known_codes()
        unknown = sorted(wanted - known)
        if not unknown:
            self.logger.debug(
                "Every required skill code is in the catalogue: %s.",
                ", ".join(sorted(wanted)),
            )
            return
        self.logger.warning(
            "Refused a requirement naming %d unknown skill code(s): %s.",
            len(unknown),
            ", ".join(unknown),
        )
        raise MTSkillTypeUnknownCode(
            f"Unknown skill code(s): {', '.join(unknown)}. "
            f"The catalogue offers: {', '.join(sorted(known)) or 'nothing yet'}."
        )

    async def create(self, skill_type: SkillType) -> SkillType:
        """Add a skill to the catalogue.

        Args:
            skill_type (SkillType): The entry to add.

        Returns:
            SkillType: The stored entry.

        Raises:
            MTSkillTypeAlreadyExists: If the code is already taken.
        """
        self.logger.info(
            "Adding skill type %s to the catalogue.",
            skill_type.code,
        )
        try:
            return await self.skills.create(skill_type)
        except IntegrityError as exc:
            self.logger.warning(
                "Refused to add %s: the code is already used.",
                skill_type.code,
            )
            raise MTSkillTypeAlreadyExists(
                f"A skill already uses the code {skill_type.code!r}."
            ) from exc

    async def get(self, type_id: str) -> SkillType:
        """Return one catalogue entry.

        Args:
            type_id (str): The entry wanted.

        Returns:
            SkillType: The entry.

        Raises:
            MTSkillTypeNotFound: If no such entry exists.
        """
        found = await self.skills.get(type_id)
        if found is None:
            self.logger.warning("Skill type %s does not exist.", type_id)
            raise MTSkillTypeNotFound(f"No skill type {type_id!r} exists.")
        return found

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        include_inactive: bool = False,
        skill_filter: Optional[SkillTypeFilter] = None,
    ) -> List[SkillType]:
        """Return a page of the catalogue.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            include_inactive (bool): Whether retired entries are included.
            skill_filter (Optional[SkillTypeFilter]): The screen's filter.

        Returns:
            List[SkillType]: The matching entries, ordered by label.
        """
        self.logger.debug(
            "Listing the skill catalogue: page=%d include_inactive=%s.",
            page,
            include_inactive,
        )
        return await self.skills.list(
            page=page,
            size=size,
            include_inactive=include_inactive,
            skill_filter=skill_filter,
        )

    async def update(
        self,
        type_id: str,
        label: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> SkillType:
        """Change what a catalogue entry says.

        Args:
            type_id (str): The entry to change.
            label (Optional[str]): The new display name, or ``None`` to leave
                it alone.
            description (Optional[str]): The new description, or ``None`` to
                leave it alone.
            is_active (Optional[bool]): Whether it may still be required, or
                ``None`` to leave it alone.

        Returns:
            SkillType: The updated entry.

        Raises:
            MTSkillTypeNotFound: If no such entry exists.

        Notes:
            ``code`` is not a parameter, so no call can rename it. The entry is
            loaded and copied field by field rather than replaced wholesale,
            which is what lets the caller send a partial edit without the
            omitted fields being reset to their defaults.
        """
        existing = await self.get(type_id)
        updated = existing.model_copy(
            update={
                "label": existing.label if label is None else label,
                "description": (
                    existing.description if description is None else description  # noqa: E501
                ),
                "is_active": existing.is_active if is_active is None else is_active,  # noqa: E501
            }
        )
        if existing.is_active and updated.is_active is False:
            self.logger.warning(
                "Skill %s is retired; no new requirement may name it, and the "
                "%d assistant(s) who declared it keep it.",
                existing.code,
                len(await self._holders_of(existing.code)),
            )
        stored = await self.skills.update(updated)
        if stored is None:
            self.logger.error(
                "Skill type %s vanished between the read and the write.",
                type_id,
            )
            raise MTSkillTypeNotFound(f"No skill type {type_id!r} exists.")
        self.logger.info("Updated skill type %s (%s).", type_id, stored.code)
        return stored

    async def delete(self, type_id: str) -> None:
        """Remove a catalogue entry that nothing refers to.

        Args:
            type_id (str): The entry to remove.

        Raises:
            MTSkillTypeNotFound: If no such entry exists.
            MTSkillTypeInUse: If an assistant has declared it or a service
                requires it.

        Notes:
            - **The check stands in for a foreign key that cannot exist.** The
              references live in a JSON array and in a nullable column with no
              constraint on it, so nothing at the database level would stop this
              leaving a requirement pointing at nothing — and a requirement
              pointing at nothing fails every planning run it touches.
            - The refusal names *what* still refers to the entry, and says
              retiring is the alternative. "Cannot delete" with no reason is the
              message somebody works around by deleting the assistant's declared
              skill instead.
        """
        existing = await self.get(type_id)
        holders = await self._holders_of(existing.code)
        services = await self._services_requiring(existing.code)
        if holders or services:
            self.logger.warning(
                "Refused to delete skill %s: %d holder(s) and %d service(s) "
                "still refer to it.",
                existing.code,
                len(holders),
                len(services),
            )
            raise MTSkillTypeInUse(
                f"The skill {existing.code!r} is still declared by "
                f"{len(holders)} assistant(s) and required by "
                f"{len(services)} service(s). Retire it instead, which stops "
                f"it being required again without stranding the declarations "
                f"that name it."
            )
        removed = await self.skills.delete(type_id)
        if not removed:
            self.logger.error(
                "Skill type %s vanished between the read and the delete.",
                type_id,
            )
            raise MTSkillTypeNotFound(f"No skill type {type_id!r} exists.")
        self.logger.info("Deleted skill type %s (%s).", type_id, existing.code)
