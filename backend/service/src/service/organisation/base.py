from __future__ import annotations

# Standard library imports
from abc import ABC, abstractmethod
from logging import Logger, getLogger
from typing import (  # noqa: E501
    ClassVar,
    Generic,
    List,
    Optional,
    Protocol,
    Type,
    TypeVar,
    runtime_checkable,
)

# First-party imports
from models.auth.user import User


@runtime_checkable
class CompanyScopedEntity(Protocol):
    """What a team or a site exposes to be owned and named.

    Attributes:
        id (Optional[str]): Identifier, ``None`` before the entity is stored.
        company_id (str): The company the entity belongs to.
        name (str): What the entity is called.
    """

    id: Optional[str]
    company_id: str
    name: str


TEntity = TypeVar("TEntity", bound=CompanyScopedEntity)
TView = TypeVar("TView")


class AbstractOrganisationService(ABC, Generic[TEntity, TView]):
    """Shared read/write contract and rules for a company's teams and sites.

    Attributes:
        entity_label (ClassVar[str]): What to call the entity in a message, e.g.
            ``"team"`` or ``"agency"``.
        unreachable_exc (ClassVar[Type[Exception]]): Raised by :meth:`_owned`
            when the entity does not exist or belongs to another company.
        name_taken_exc (ClassVar[Type[Exception]]): Raised by
            :meth:`_assert_name_free` when the name is already in use.
        logger (Logger): Logger for the operations here.

    Notes:
        - Both :class:`~service.organisation.teams.TeamService` and
          :class:`~service.organisation.agencies.AgencyService` fetch an entity,
          refuse one that does not exist or belongs to another company, and
          refuse a name a sibling entity already holds. Written twice, those two
          checks could drift. This is the one place they are spelled.
        - **``unreachable_exc`` alone stands in for two historically distinct
          exception classes.** ``TeamService.get`` used to raise
          ``MTTeamNotFound`` for both "missing" and "wrong company", while
          ``AgencyService._owned`` raised ``MTAgencyForbidden`` for the same
          pair — both are answered as a 404, so the difference was only ever in
          the name. Each subclass keeps its own historical class here.
        - :meth:`get` and :meth:`list` default to ownership alone. A service
          whose callers see less than their whole company — a team narrowed to
          a manager's own, or to the one an assistant sits on — overrides them.
          :meth:`view` and :meth:`views` are the same read, projected: neither
          is overridden, only the :meth:`_to_view`/:meth:`_to_views` projection.
    """

    entity_label: ClassVar[str]
    unreachable_exc: ClassVar[Type[Exception]]
    name_taken_exc: ClassVar[Type[Exception]]

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the service.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("%s created.", type(self).__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    @abstractmethod
    async def _get(self, entity_id: str) -> Optional[TEntity]:
        """Return the entity by identifier, or ``None``.

        Args:
            entity_id (str): The entity to read.

        Returns:
            Optional[TEntity]: The entity, or ``None`` when it does not exist.
        """

    @abstractmethod
    async def _list_for_company(
        self, company_id: str, *, page: int = 1, size: Optional[int] = None
    ) -> List[TEntity]:
        """Return a company's entities, for the name-uniqueness scan.

        Args:
            company_id (str): The company being checked.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[TEntity]: The company's entities.
        """

    async def _owned(self, entity_id: str, caller: User) -> TEntity:
        """Return an entity, having proved it is the caller's company's.

        Args:
            entity_id (str): The entity to read.
            caller (User): The authenticated caller.

        Returns:
            TEntity: The entity.

        Raises:
            Exception: ``self.unreachable_exc``, if no such entity exists or it
                belongs to another company.
        """
        entity = await self._get(entity_id)
        if entity is None:
            self.logger.warning("%s %s does not exist.", self.entity_label, entity_id)  # noqa: E501
            raise self.unreachable_exc(f"No {self.entity_label} {entity_id!r} exists.")  # noqa: E501
        if entity.company_id != caller.company_id:
            self.logger.warning(
                "Account %s of company %s tried to reach %s %s of company %s.",
                caller.id,
                caller.company_id,
                self.entity_label,
                entity_id,
                entity.company_id,
            )
            raise self.unreachable_exc(f"No {self.entity_label} {entity_id!r} exists.")  # noqa: E501
        return entity

    async def _assert_name_free(
        self, company_id: str, name: str, except_id: Optional[str] = None
    ) -> None:
        """Refuse a name another of the company's entities already uses.

        Args:
            company_id (str): The company being checked.
            name (str): The proposed name.
            except_id (Optional[str]): An entity allowed to hold the name.

        Raises:
            Exception: ``self.name_taken_exc``, if the name is in use.
        """
        for entity in await self._list_for_company(company_id, size=None):
            if entity.name == name and entity.id != except_id:
                self.logger.warning(
                    "Company %s already has a %s named %s.",
                    company_id,
                    self.entity_label,
                    name,
                )
                raise self.name_taken_exc(
                    f"This company already has another {self.entity_label} "
                    f"named {name!r}."
                )

    @abstractmethod
    async def _to_view(self, entity: TEntity) -> TView:
        """Project one entity onto its screen representation.

        Args:
            entity (TEntity): The entity to project.

        Returns:
            TView: The entity, carrying whatever a screen adds to it.
        """

    @abstractmethod
    async def _to_views(self, entities: List[TEntity], caller: User) -> List[TView]:
        """Project a page of entities onto their screen representation.

        Args:
            entities (List[TEntity]): The page to project.
            caller (User): The authenticated caller, for a grouped count keyed
                on their company.

        Returns:
            List[TView]: The page, each entity carrying whatever a screen adds
            to it.

        Notes:
            Kept distinct from :meth:`_to_view` rather than mapped from it: a
            page's counts come from **one** grouped statement over the company,
            and calling :meth:`_to_view` once per row would turn that one
            statement into one per row.
        """

    ############################
    # Publicly Exposed Methods #
    ############################

    async def get(self, entity_id: str, caller: User) -> TEntity:
        """Return an entity the caller is allowed to read.

        Args:
            entity_id (str): The entity to read.
            caller (User): The authenticated caller.

        Returns:
            TEntity: The entity.

        Raises:
            Exception: ``self.unreachable_exc``, if no such entity exists or it
                belongs to another company.

        Notes:
            Ownership alone. A service whose callers see less than their whole
            company overrides this to narrow further.
        """
        return await self._owned(entity_id, caller)

    async def list(
        self, caller: User, page: int = 1, size: Optional[int] = None
    ) -> List[TEntity]:
        """Return the entities the caller may read.

        Args:
            caller (User): The authenticated caller.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[TEntity]: The caller's company's entities.

        Notes:
            The whole company. A service whose callers see less overrides this
            to narrow further.
        """
        return await self._list_for_company(caller.company_id, page=page, size=size)

    async def view(self, entity_id: str, caller: User) -> TView:
        """Return one entity the caller may read, ready for a screen.

        Args:
            entity_id (str): The entity to read.
            caller (User): The authenticated caller.

        Returns:
            TView: The entity, projected for a screen.

        Raises:
            Exception: ``self.unreachable_exc``, if no such entity exists or it
                belongs to another company.
        """
        entity = await self.get(entity_id, caller)
        return await self._to_view(entity)

    async def views(
        self, caller: User, page: int = 1, size: Optional[int] = None
    ) -> List[TView]:
        """Return the entities the caller may read, ready for a grid.

        Args:
            caller (User): The authenticated caller.
            page (int): One-based page number.
            size (Optional[int]): Page size.

        Returns:
            List[TView]: The entities, projected for a grid.
        """
        entities = await self.list(caller, page=page, size=size)
        return await self._to_views(entities, caller)

    @abstractmethod
    async def create(self, entity: TEntity, caller: User) -> TEntity:
        """Create an entity for the caller's company.

        Args:
            entity (TEntity): The entity to create.
            caller (User): The authenticated caller.

        Returns:
            TEntity: The stored entity.
        """

    @abstractmethod
    async def update(self, entity: TEntity, caller: User) -> TEntity:
        """Change a stored entity.

        Args:
            entity (TEntity): The entity, carrying its identifier.
            caller (User): The authenticated caller.

        Returns:
            TEntity: The stored entity.
        """

    @abstractmethod
    async def delete(self, entity_id: str, caller: User) -> None:
        """Remove a stored entity.

        Args:
            entity_id (str): The entity to remove.
            caller (User): The authenticated caller.
        """
