from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Dict, Optional, Union

# Third-party imports
from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    JsonValue,
    field_serializer,
    field_validator,
    model_validator,
)

# First-party imports
from models.auth.exceptions import (
    MTUserInvalidAccountOrigin,
    MTUserInvalidCompanyId,
    MTUserInvalidDate,
    MTUserInvalidEmail,
    MTUserInvalidFullName,
    MTUserInvalidHashedPassword,
    MTUserInvalidHcaId,
    MTUserInvalidId,
    MTUserInvalidMustChangePassword,
    MTUserInvalidRole,
    MTUserRoleHcaRequiresHcaId,
    MTUserStaffAccountNeedsChange,
)
from models.enums import AccountOrigin, UserRole


class User(BaseModel):
    """An account able to sign in to the backend.

    Attributes:
        id (Optional[str]): Identifier, populated on read from the store.
        email (EmailStr): Sign-in address; unique across accounts.
        full_name (str): Display name.
        hashed_password (Optional[str]): Bcrypt hash of the password.
        role (UserRole): What the account may do.
        is_active (bool): Whether sign-in is permitted.
        hca_id (Optional[str]): The assistant record this account belongs to.
        company_id (Optional[str]): The company this account belongs to.
        account_origin (AccountOrigin): Whether the account was
            self-registered or created by staff.
        must_change_password (bool): Whether the holder must set a new
            password before the account can do anything else.
        password_changed_at (Optional[datetime]): When the holder last
            chose their own password; ``None`` if they never have.
            Required for an assistant account, and absent otherwise.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        ``hca_id`` is what makes row-level access possible. An assistant may
        only read their own planning, and the check compares this field with
        the assistant whose planning was asked for — a route guard alone would
        only prove the caller is *an* assistant, not the right one. The
        cross-field validator therefore refuses to build an assistant account
        that carries no link, since such an account could never be checked.

        ``hashed_password`` is optional so a user record can exist before a
        password is set, but it is never serialised: see
        :meth:`to_public_dict`.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    email: EmailStr = Field(description="Sign-in address; unique across accounts.")
    full_name: str = Field(description="Display name.")
    hashed_password: Optional[str] = Field(
        default=None,
        description="Bcrypt hash of the password.",
    )
    role: UserRole = Field(
        default=UserRole.HCA,
        description="What the account may do.",
    )
    is_active: bool = Field(
        default=True,
        description="Whether sign-in is permitted.",
    )
    hca_id: Optional[str] = Field(
        default=None,
        description="The assistant record this account belongs to.",
    )
    company_id: Optional[str] = Field(
        default=None,
        description="The company this account belongs to.",
    )
    account_origin: AccountOrigin = Field(
        default=AccountOrigin.SELF_REGISTERED,
        description="Whether the account was self-registered or staff-created.",
    )
    must_change_password: bool = Field(
        default=False,
        description="Whether the password must be changed before anything else.",
    )
    password_changed_at: Optional[datetime] = Field(
        default=None,
        description="When the holder last chose their own password.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="Creation timestamp, set by the store.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last-update timestamp, set by the store.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is persisted.

        Raises:
            MTUserInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("email", mode="before")
    def validate_email(cls, value: Optional[str]) -> str:
        """Validates that ``email`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``email`` value.

        Returns:
            str: The stripped, lower-cased address.

        Raises:
            MTUserInvalidEmail: If ``value`` is not a non-empty string.

        Notes:
            The address is lower-cased so sign-in is case-insensitive and the
            uniqueness index cannot be defeated by changing capitalisation.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty string."
            )
        return value.strip().lower()

    @field_validator("full_name", mode="before")
    def validate_full_name(cls, value: Optional[str]) -> str:
        """Validates that ``full_name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``full_name`` value.

        Returns:
            str: The stripped display name.

        Raises:
            MTUserInvalidFullName: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidFullName(
                f"Invalid full_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("hashed_password", mode="before")
    def validate_hashed_password(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``hashed_password`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``hashed_password`` value.

        Returns:
            Optional[str]: The hash, or ``None`` when no password is set.

        Raises:
            MTUserInvalidHashedPassword: If ``value`` is neither ``None`` nor a
                non-empty string.

        Notes:
            The value is not stripped: a hash is opaque, and trimming it would
            silently corrupt a credential rather than reject it.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidHashedPassword(
                "Invalid hashed_password. Must be a non-empty string or None."
            )
        return value

    @field_validator("role", mode="before")
    def validate_role(cls, value: Union[str, UserRole, None]) -> UserRole:
        """Validates that ``role`` is a known user role.

        Args:
            value (Union[str, UserRole, None]): Raw ``role`` value. ``None``
                falls back to :attr:`UserRole.HCA`.

        Returns:
            UserRole: The coerced role.

        Raises:
            MTUserInvalidRole: If ``value`` is not a known role.

        Notes:
            The default is the least-privileged role. A typo in a stored role
            must never fail open into a manager or admin account.
        """
        if value is None:
            return UserRole.HCA
        if isinstance(value, UserRole):
            return value
        try:
            return UserRole(value)
        except ValueError:
            raise MTUserInvalidRole(
                f"Invalid role: {value!r}. Must be one of: "
                f"{', '.join(UserRole.values())}."
            ) from None

    @field_validator("hca_id", mode="before")
    def validate_hca_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``hca_id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``hca_id`` value.

        Returns:
            Optional[str]: The assistant identifier, or ``None``.

        Raises:
            MTUserInvalidHcaId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidHcaId(
                f"Invalid hca_id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``company_id``, when given, is a non-empty string.

        Args:
            value (Optional[str]): Raw ``company_id`` value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTUserInvalidCompanyId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserInvalidCompanyId(
                f"Invalid company_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("account_origin", mode="before")
    def validate_account_origin(
        cls, value: Union[str, AccountOrigin, None]
    ) -> AccountOrigin:
        """Validates that ``account_origin`` is a known origin.

        Args:
            value (Union[str, AccountOrigin, None]): Raw origin value.

        Returns:
            AccountOrigin: The coerced origin.

        Raises:
            MTUserInvalidAccountOrigin: If ``value`` is not a known origin.
        """
        if value is None:
            return AccountOrigin.SELF_REGISTERED
        if isinstance(value, AccountOrigin):
            return value
        try:
            return AccountOrigin(value)
        except ValueError:
            raise MTUserInvalidAccountOrigin(
                f"Invalid account_origin: {value!r}. Must be one of: "
                f"{', '.join(AccountOrigin.values())}."
            ) from None

    @field_validator("must_change_password", mode="before")
    def validate_must_change_password(cls, value: Optional[bool]) -> bool:
        """Validates that the forced-change flag is a boolean.

        Args:
            value (Optional[bool]): Raw flag value.

        Returns:
            bool: The flag.

        Raises:
            MTUserInvalidMustChangePassword: If ``value`` is neither ``None``
                nor a boolean.

        Notes:
            Strings are refused rather than coerced. ``"false"`` is truthy, and
            a stored ``"false"`` read as "must change" would lock somebody out
            of their own account — while the reverse would quietly waive the
            change this whole flag exists to force.
        """
        if value is None:
            return False
        if not isinstance(value, bool):
            raise MTUserInvalidMustChangePassword(
                f"Invalid must_change_password: {value!r}. Must be a boolean."
            )
        return value

    @field_validator("created_at", "updated_at", "password_changed_at", mode="before")
    def validate_date(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a timestamp is a datetime, an ISO string or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp value.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic to
            parse.

        Raises:
            MTUserInvalidDate: If ``value`` is neither ``None`` nor a
                datetime-like value.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise MTUserInvalidDate(
            f"Invalid timestamp: {value!r}. "
            f"Must be a datetime, an ISO-8601 string, or None."
        )

    @model_validator(mode="after")
    def check_staff_account_must_change(self) -> User:
        """Ensure a staff-created account is made to choose its own password.

        Returns:
            User: ``self`` for chaining.

        Raises:
            MTUserStaffAccountNeedsChange: If the account was created by staff,
                already carries a credential, and is not required to change it.

        Notes:
            **The specification's "MANDATORY" is enforced here, at
            construction.** An account whose password was typed by somebody
            else is a credential two people know; requiring the change is what
            ends that, and a flag that can be left off by whoever writes the
            next admin screen is not a requirement.

            The check applies only while the temporary password is still the
            one in force. Once ``password_changed_at`` is set the holder has
            chosen their own, so the flag is correctly off — without that
            second condition an account could not be *read back* after changing
            its password, which is a validator making a legitimate state
            unrepresentable.

            It also applies only once a credential exists: an account being
            assembled before its temporary password is set has nothing to
            change yet.
        """
        if (
            self.account_origin is AccountOrigin.CREATED_BY_STAFF
            and self.hashed_password
            and not self.password_changed_at
            and not self.must_change_password
        ):
            raise MTUserStaffAccountNeedsChange(
                "Invalid must_change_password: an account created by an "
                "administrator or manager must change its temporary password "
                "at first sign-in."
            )
        return self

    @model_validator(mode="after")
    def check_hca_link(self) -> User:
        """Ensure an assistant account is linked to an assistant record.

        Returns:
            User: ``self`` for chaining.

        Raises:
            MTUserRoleHcaRequiresHcaId: If the role is
                :attr:`UserRole.HCA` and no ``hca_id`` is set.

        Notes:
            Without the link there is nothing to compare a planning request
            against, so the account could read no planning at all — or, worse,
            a naive check could read it as "unrestricted". Refusing to build
            the account removes that state entirely.
        """
        if self.role is UserRole.HCA and self.hca_id is None:
            raise MTUserRoleHcaRequiresHcaId(
                "Invalid hca_id: an account with the 'hca' role must be linked "
                "to an assistant record, or its planning access cannot be "
                "checked."
            )
        return self

    @field_serializer("created_at", "updated_at")
    def serialize_date(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_public_dict(self) -> Dict[str, JsonValue]:
        """Return a JSON-serializable view of the account without its secret.

        Returns:
            Dict[str, JsonValue]: Every field except ``hashed_password``.

        Notes:
            This is the only shape an account may leave the backend in. The
            password hash is excluded here rather than at each call site, so a
            new endpoint cannot leak it by forgetting to.
        """
        return self.model_dump(mode="json", exclude={"hashed_password"})

    def is_manager(self) -> bool:
        """Return whether the account has manager privileges or above.

        Returns:
            bool: ``True`` for a manager or an admin.
        """
        return self.role.has_at_least(UserRole.MANAGER)

    def is_admin(self) -> bool:
        """Return whether the account is an administrator.

        Returns:
            bool: ``True`` only for the admin role.

        Notes:
            Compared by identity rather than by rank: admin is the highest
            role, so the two agree today, but an identity check keeps the
            meaning exact if a higher role is ever added.
        """
        return self.role is UserRole.ADMIN

    def owns_hca(self, hca_id: str) -> bool:
        """Return whether the account may read a given assistant's planning.

        Args:
            hca_id (str): The assistant whose planning is being requested.

        Returns:
            bool: ``True`` when the account is a manager or admin, or when it
            is the assistant's own account.

        Notes:
            This is the row-level rule behind "an assistant cannot see another
            assistant's planning". It lives on the model so every caller
            answers the question the same way.
        """
        if self.role is not UserRole.HCA:
            return True
        return self.hca_id is not None and self.hca_id == hca_id
