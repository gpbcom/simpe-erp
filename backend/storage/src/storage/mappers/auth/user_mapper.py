from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import Optional

# First-party imports
from models.auth.user import User
from models.enums import UserRole
from storage.mappers.base_mapper import BaseMapper
from storage.orm.auth.user_row import UserRow


class UserMapper(BaseMapper[User, UserRow]):
    """Converts between :class:`User` and :class:`UserRow`.

    Notes:
        - The password hash crosses this boundary in both directions, unlike
          anywhere else in the stack: the repository needs it to authenticate a
          sign-in. Everything above the service layer uses
          :meth:`~models.auth.user.User.to_public_dict`, which drops it.
        - Nothing is logged about the credential — not its value, not its
          length, not its shape. The one line that mentions it says only that
          none was supplied, which is a fact about the request rather than
          about the secret.
        - An account **is** a person-shaped record now —
          :class:`~models.auth.user.User` extends
          :class:`~models.base.person.Person` — but it still maps straight off
          :class:`~storage.mappers.base_mapper.BaseMapper` rather than through
          the person mapper. The address and telephone columns that mapper
          reads do not exist on ``users``: the two fields are optional on an
          account and are not stored, because the contact details of somebody
          the agency schedules live on their assistant record.
        - The display name is **two columns**, ``first_name`` and
          ``last_name``, and is recomposed by
          :meth:`~models.auth.user.User.full_name`. Nothing here splits or
          joins it — the model does both, so the store and the API cannot
          disagree about where the surname starts.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(model_class=User, row_class=UserRow, logger=logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: UserRow) -> User:
        """Build a user from a row's columns.

        Args:
            row (UserRow): The row to read.

        Returns:
            User: The domain model, carrying the password hash.

        Raises:
            MTInvalidUserException: If a stored value no longer satisfies the
                model's validators.

        Notes:
            An assistant account stored without an ``hca_id`` fails here rather
            than silently loading, because the model refuses to build one — an
            account that cannot be checked against a planning is worse than an
            account that cannot load.
        """
        self.logger.debug(
            "Building a user from row %s (role %s, active %s).",
            row.id,
            row.role,
            row.is_active,
        )
        return User(
            id=row.id,
            email=row.email,
            first_name=row.first_name,
            last_name=row.last_name,
            hashed_password=row.hashed_password,
            role=row.role,
            is_active=row.is_active,
            hca_id=row.hca_id,
            customer_id=row.customer_id,
            company_id=row.company_id,
            account_origin=row.account_origin,
            photo_url=row.photo_url,
            language=row.language,
            must_change_password=row.must_change_password,
            password_changed_at=self.timestamps.to_utc(row.password_changed_at),
            created_at=self.timestamps.to_utc(row.created_at),
            updated_at=self.timestamps.to_utc(row.updated_at),
        )

    def _apply_fields(self, row: UserRow, model: User) -> None:
        """Write a user's fields onto a row.

        Args:
            row (UserRow): The row to write to.
            model (User): The model carrying the values.

        Notes:
            The password hash is only written when the model carries one. An
            update built from a public view has ``hashed_password = None``, and
            copying that through would silently lock the account out — which is
            why the row keeps whatever it already holds instead.
        """
        role = UserRole(model.role)
        self.logger.debug(
            "Applying a user onto row %s (role %s, active %s).",
            row.id,
            role.value,
            model.is_active,
        )
        row.email = str(model.email)
        row.first_name = model.first_name
        row.last_name = model.last_name
        row.role = role.value
        row.is_active = model.is_active
        row.hca_id = model.hca_id
        row.customer_id = model.customer_id
        row.company_id = model.company_id
        row.account_origin = model.account_origin.value
        row.photo_url = str(model.photo_url) if model.photo_url is not None else None  # noqa: E501
        row.language = model.language.value
        row.must_change_password = model.must_change_password
        row.password_changed_at = model.password_changed_at
        if model.hashed_password is not None:
            row.hashed_password = model.hashed_password
        else:
            self.logger.warning(
                "No credential supplied for user row %s: "  # noqa: E501
                "keeping the stored one.",
                row.id,
            )
        if not model.is_active:
            self.logger.info(
                "User row %s is stored as inactive: sign-in is refused.",
                row.id,
            )
