from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third-party imports
from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# First-party imports
from models.auth.user import User
from models.enums import UserRole
from storage.mappers.auth.user_mapper import UserMapper
from storage.orm.auth.user_row import UserRow
from storage.repositories.base import BaseRepository


class UserRepository(BaseRepository[UserRow]):
    """Reads and writes accounts.

    Attributes:
        mapper (UserMapper): Converts between rows and domain models.

    Notes:
        :meth:`get_by_email` is the sign-in path, and the only read that
        returns an account carrying its password hash for comparison. Every
        other consumer works from
        :meth:`~models.auth.user.User.to_public_dict`.
    """

    def __init__(self, session: AsyncSession, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            session (AsyncSession): The session to run statements on.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.logger = logger if logger else getLogger(__name__)
        super().__init__(session=session, row_class=UserRow)
        self.mapper = UserMapper()

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_query(self, role: Optional[UserRole] = None) -> Select[Tuple[UserRow]]:
        """Build the filtered select shared by the listing methods.

        Args:
            role (Optional[UserRole]): Restrict to one role.

        Returns:
            Select[Tuple[UserRow]]: The filtered statement, without ordering or pagination.
        """
        statement = select(UserRow)
        if role is not None:
            statement = statement.where(UserRow.role == role.value)
        return statement

    ############################
    # Publicly Exposed Methods #
    ############################

    async def list_supervisors(self, company_id: Optional[str] = None) -> List[User]:
        """Return the accounts that may rule on an agency's work.

        Args:
            company_id (Optional[str]): Restrict to one agency. ``None``
                returns every supervisor, whichever agency they belong to.

        Returns:
            List[User]: The active manager and administrator accounts.

        Notes:
            - Managers **and** administrators, because an administrator
              outranks a manager and can do everything they can. A fan-out that
              reached only managers would silently skip an agency run by one
              administrator alone — which is most small agencies.
            - Inactive accounts are excluded. A suspended account cannot sign
              in, so a notification addressed to it is one nobody will ever
              read, and it would sit in the unread count for ever.
        """
        statement = select(UserRow).where(
            UserRow.role.in_([UserRole.MANAGER.value, UserRole.ADMIN.value]),
            UserRow.is_active.is_(True),
        )
        if company_id is not None:
            statement = statement.where(UserRow.company_id == company_id)
        rows = await self._fetch_all(statement)
        if not rows:
            self.logger.error(
                "No active supervisor found for company %s; nobody can be told "
                "about work waiting for a decision.",
                company_id,
            )
        else:
            self.logger.debug(
                "Found %d supervisor(s) for company %s.", len(rows), company_id
            )
        return self.mapper.to_models(rows)

    async def create(self, user: User) -> User:
        """Insert a new account.

        Args:
            user (User): The account to store.

        Returns:
            User: The stored account, carrying its generated identifier.

        Raises:
            SQLAlchemyError: If the insert fails — notably when the email is
                already registered.
        """
        self.logger.info("Creating user %s with role %s.", user.email, user.role.value)
        row = self.mapper.to_row(user)
        self.session.add(row)
        await self.session.flush()
        self.logger.debug("Created user row %s.", row.id)
        return self.mapper.to_model(row)

    async def get(self, user_id: str) -> Optional[User]:
        """Return an account by identifier.

        Args:
            user_id (str): The identifier to look up.

        Returns:
            Optional[User]: The account, or ``None`` when absent.
        """
        row = await self._get_row(user_id)
        if row is None:
            self.logger.warning("User %s not found.", user_id)
            return None
        return self.mapper.to_model(row)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Return an account by sign-in address.

        Args:
            email (str): The address to look up. Matched case-insensitively.

        Returns:
            Optional[User]: The account, carrying its password hash, or
            ``None`` when no account is registered under the address.

        Notes:
            The address is lower-cased before the lookup because that is the
            form the model stores. A sign-in typed with different
            capitalisation must still find the account.
        """
        normalized = email.strip().lower()
        self.logger.debug("Looking up user by email %s.", normalized)
        statement = select(UserRow).where(UserRow.email == normalized)
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.warning("No user registered under %s.", normalized)
            return None
        return self.mapper.to_model(row)

    async def get_by_hca_id(self, hca_id: str) -> Optional[User]:
        """Return the account bound to an assistant record.

        Args:
            hca_id (str): The assistant whose account is wanted.

        Returns:
            Optional[User]: The account, or ``None`` when the assistant has
            none.

        Notes:
            At most one account points at a given assistant. Nothing in the
            schema enforces that — ``hca_id`` is indexed but not unique — so
            this returns the first match rather than asserting there is only
            one: a duplicate is a data problem to fix, not a reason to fail the
            deletion that discovered it.

            This exists so removing an assistant can take their account with
            them. Before it did, the foreign key refused the delete and the
            only way through was to find the account by email on another
            screen.
        """
        self.logger.debug("Looking up the account bound to assistant %s.", hca_id)
        statement = select(UserRow).where(UserRow.hca_id == hca_id)
        row = await self._fetch_one(statement)
        if row is None:
            self.logger.debug("Assistant %s has no sign-in account.", hca_id)
            return None
        return self.mapper.to_model(row)

    async def get_by_customer_id(self, customer_id: str) -> Optional[User]:
        """Return the portal account bound to a customer record.

        Args:
            customer_id (str): The household whose account is wanted.

        Returns:
            Optional[User]: The account, or ``None`` when the household has
            none.

        Raises:
            SQLAlchemyError: If the query fails.

        Notes:
            The mirror of :meth:`get_by_hca_id`, and it answers two questions:
            whether an invitation would be a second set of credentials for one
            household, and what has to be deleted along with the customer —
            the foreign key is ``RESTRICT``, so a household with an account
            cannot be removed until the account is.
        """
        self.logger.debug("Looking up the account bound to customer %s.", customer_id)
        statement = select(UserRow).where(UserRow.customer_id == customer_id)
        try:
            row = await self._fetch_one(statement)
        except SQLAlchemyError:
            self.logger.error("Reading the account of customer %s failed.", customer_id)
            raise
        if row is None:
            self.logger.info("Customer %s has no portal account.", customer_id)
            return None
        self.logger.warning(
            "Customer %s already holds portal account %s.", customer_id, row.id
        )
        return self.mapper.to_model(row)

    async def update(self, user: User) -> Optional[User]:
        """Update an existing account.

        Args:
            user (User): The account to store, carrying its identifier.

        Returns:
            Optional[User]: The updated account, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.
        """
        if user.id is None:
            self.logger.warning("Update requested for a user with no id.")
            return None
        row = await self._get_row(user.id)
        if row is None:
            self.logger.warning("Update requested for absent user %s.", user.id)
            return None
        self.mapper.apply_to_row(row, user)
        await self.session.flush()
        self.logger.info("Updated user %s.", user.id)
        return self.mapper.to_model(row)

    async def set_role(self, user_id: str, role: UserRole) -> Optional[User]:
        """Change an account's role.

        Args:
            user_id (str): The account to change.
            role (UserRole): The new role.

        Returns:
            Optional[User]: The updated account, or ``None`` when absent.

        Notes:
            This is the promote-to-manager path, restricted to admins at the
            route. A narrow method rather than a general update: a role change
            must not be a side effect of saving an unrelated edit.
        """
        row = await self._get_row(user_id)
        if row is None:
            self.logger.warning("Role change requested for absent user %s.", user_id)
            return None
        self.logger.info(
            "Changing user %s role from %s to %s.", user_id, row.role, role.value
        )
        row.role = role.value
        await self.session.flush()
        return self.mapper.to_model(row)

    async def set_active(self, user_id: str, is_active: bool) -> Optional[User]:
        """Enable or disable sign-in for an account.

        Args:
            user_id (str): The account to change.
            is_active (bool): Whether sign-in is permitted.

        Returns:
            Optional[User]: The updated account, or ``None`` when absent.
        """
        row = await self._get_row(user_id)
        if row is None:
            self.logger.warning("Active change requested for absent user %s.", user_id)
            return None
        self.logger.info("Setting user %s active to %s.", user_id, is_active)
        row.is_active = is_active
        await self.session.flush()
        return self.mapper.to_model(row)

    async def set_photo_url(
        self, user_id: str, photo_url: Optional[str]
    ) -> Optional[User]:
        """Point an account at a stored portrait, or clear it.

        Args:
            user_id (str): The account to change.
            photo_url (Optional[str]): The object-store URL, or ``None`` to
                remove the portrait.

        Returns:
            Optional[User]: The updated account, or ``None`` when absent.

        Raises:
            SQLAlchemyError: If the update fails.

        Notes:
            A narrow method, like :meth:`set_role` and :meth:`set_active`. The
            portrait is uploaded on its own endpoint, and routing it through
            :meth:`update` would mean re-writing every other column — including
            the password hash, which an account read back through a public view
            no longer carries.
        """
        row = await self._get_row(user_id)
        if row is None:
            self.logger.warning("Portrait link requested for absent user %s.", user_id)
            return None
        self.logger.info(
            "Setting the portrait of user %s to %s.", user_id, photo_url or "none"
        )
        row.photo_url = photo_url
        await self.session.flush()
        return self.mapper.to_model(row)

    async def list(
        self,
        page: int = 1,
        size: Optional[int] = None,
        role: Optional[UserRole] = None,
    ) -> List[User]:
        """Return a page of accounts.

        Args:
            page (int): One-based page number.
            size (Optional[int]): Page size.
            role (Optional[UserRole]): Restrict to one role.

        Returns:
            List[User]: The matching accounts, ordered by email.
        """
        self.logger.debug(
            "Listing users: page=%d role=%s.", page, role.value if role else None
        )
        statement = self._build_query(role=role).order_by(UserRow.email)
        rows = await self._fetch_all(self._paginate(statement, page, size))
        if not rows:
            self.logger.warning("No user matched the query.")
        return self.mapper.to_models(rows)

    async def count(self, role: Optional[UserRole] = None) -> int:
        """Return how many accounts match a query.

        Args:
            role (Optional[UserRole]): Restrict to one role.

        Returns:
            int: The number of matching accounts.
        """
        return await self._count(self._build_query(role=role))

    async def count_admins(self) -> int:
        """Return how many admin accounts exist.

        Returns:
            int: The number of accounts holding the admin role.

        Notes:
            Used to refuse the demotion or deactivation of the last admin,
            which would otherwise leave the installation with nobody able to
            run a planning or promote a manager.
        """
        total = await self._count(self._build_query(role=UserRole.ADMIN))
        self.logger.debug("Counted %d admin account(s).", total)
        if total == 0:
            self.logger.warning(
                "No admin account exists; planning runs cannot be started."
            )
        return total

    async def delete(self, user_id: str) -> bool:
        """Delete an account.

        Args:
            user_id (str): The account to delete.

        Returns:
            bool: ``True`` when a row was deleted.

        Raises:
            SQLAlchemyError: If the delete fails.
        """
        try:
            return await self._delete_row(user_id)
        except SQLAlchemyError as exc:
            self.logger.error("Error deleting user %s: %s.", user_id, exc)
            raise

    async def count_for_company(self, company_id: str) -> int:
        """Return how many accounts belong to one agency.

        Args:
            company_id (str): The agency to count for.

        Returns:
            int: The number of accounts.

        Notes:
            A count rather than a list: the caller only needs to know whether
            the agency is empty, and reading every account to find that out
            would be a page of records fetched to be thrown away.
        """
        found = await self._count(
            select(UserRow).where(UserRow.company_id == company_id)
        )
        self.logger.debug("Agency %s has %d account(s).", company_id, found)
        return found
