from __future__ import annotations

# Standard library imports
from datetime import datetime
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_serializer, field_validator

# First-party imports
from models.auth.user import User
from models.enums import UserRole
from models.schemas.exceptions import (
    MTUserResponseInvalidDate,
    MTUserResponseInvalidEmail,
    MTUserResponseInvalidFullName,
    MTUserResponseInvalidHcaId,
    MTUserResponseInvalidId,
    MTUserResponseInvalidIsActive,
    MTUserResponseInvalidRole,
)


class UserResponse(BaseModel):
    """The shape an account leaves the API in.

    Attributes:
        id (Optional[str]): Identifier, populated once the account is stored.
        email (EmailStr): The sign-in address.
        full_name (str): The display name.
        role (UserRole): The role granted.
        is_active (bool): Whether sign-in is permitted.
        customer_id (Optional[str]): The customer record a customer account
            belongs to. The mirror of ``hca_id`` on the other axis, and
            published for the same reason: the screens ask "is this account
            bound to a person" as well as "what role is it".
        hca_id (Optional[str]): The assistant record an assistant account
            belongs to.
        company_id (Optional[str]): The agency the account belongs to.
        language (str): The language this holder reads the application, and
            receives its emailed documents, in.
        photo_url (Optional[str]): URL of the holder's portrait, when one has
            been uploaded.
        must_change_password (bool): Whether a temporary password is still in
            force.
        created_at (Optional[datetime]): Creation timestamp.
        updated_at (Optional[datetime]): Last-update timestamp.

    Notes:
        - There is no ``hashed_password`` field, and that is the point. The
          credential used to be dropped by a dump that excluded it by name. A
          field that does not exist cannot be leaked by an endpoint that forgets
          to exclude it, or re-added by a dump that stops excluding it.
        - Built through :meth:`from_user` rather than by spreading the domain
          model, so adding a field to :class:`~models.auth.user.User` never
          silently widens what the API publishes. A new field appears on the
          wire only when someone puts it here.
        - ``must_change_password`` is published because a client cannot work
          without it. The middleware answers **403 on every route but the
          password change** while the flag is set, so a client that cannot read
          it can only discover the state by being refused — it has to send a
          request it knows will fail, and then pattern-match the error body.
          Publishing the flag lets the sign-in screen go straight to the change
          form. It says nothing secret: the holder of the credential is the one
          being told they must replace it.
        - ``company_id`` scopes what the client asks for. A manager's queues are
          their agency's, and without it the client cannot tell whether it is
          looking at everything or at one company's slice.
        - ``photo_url`` is published as **plain text**, not as a URL type. It is
          read by a browser that puts it straight into an ``img`` source, and
          the model has already refused any value the object store did not
          issue — so there is nothing left here for a URL type to check.
    """

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated once the account is stored.",
    )
    email: EmailStr = Field(description="The sign-in address.")
    full_name: str = Field(description="The display name.")
    role: UserRole = Field(description="The role granted.")
    is_active: bool = Field(description="Whether sign-in is permitted.")
    hca_id: Optional[str] = Field(
        default=None,
        description="The assistant record an assistant account belongs to.",
    )
    customer_id: Optional[str] = Field(
        default=None,
        description="The customer record a customer account belongs to.",
    )
    company_id: Optional[str] = Field(
        default=None,
        description="The agency the account belongs to.",
    )
    language: str = Field(
        default="fr",
        description="The language this holder reads the application in.",
    )
    photo_url: Optional[str] = Field(
        default=None,
        description="URL of the holder's portrait in the object store.",
    )
    must_change_password: bool = Field(
        default=False,
        description="Whether a temporary password is still in force.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="Creation timestamp.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last-update timestamp.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTUserResponseInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserResponseInvalidId(
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
            MTUserResponseInvalidEmail: If ``value`` is not a non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUserResponseInvalidEmail(
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
            MTUserResponseInvalidFullName: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTUserResponseInvalidFullName(
                f"Invalid full_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("role", mode="before")
    def validate_role(cls, value: Union[str, UserRole, None]) -> UserRole:
        """Validates that ``role`` is a known user role.

        Args:
            value (Union[str, UserRole, None]): Raw ``role`` value.

        Returns:
            UserRole: The coerced role.

        Raises:
            MTUserResponseInvalidRole: If ``value`` is not a known role.
        """
        if isinstance(value, UserRole):
            return value
        try:
            return UserRole(value)
        except ValueError:
            raise MTUserResponseInvalidRole(
                f"Invalid role: {value!r}. Must be one of: "
                f"{', '.join(UserRole.values())}."
            ) from None

    @field_validator("is_active", mode="before")
    def validate_is_active(cls, value: Optional[bool]) -> bool:
        """Validates that ``is_active`` is a boolean.

        Args:
            value (Optional[bool]): Raw ``is_active`` value.

        Returns:
            bool: The validated flag.

        Raises:
            MTUserResponseInvalidIsActive: If ``value`` is not a boolean.

        Notes:
            ``0`` and ``"false"`` are rejected rather than coerced. A client
            reading this field decides whether to show an account as suspended,
            and a truthy string would flip that silently.
        """
        if not isinstance(value, bool):
            raise MTUserResponseInvalidIsActive(
                f"Invalid is_active: {value!r}. Must be a boolean."
            )
        return value

    @field_validator("hca_id", "customer_id", "company_id", mode="before")
    def validate_hca_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that a linked identifier is ``None`` or non-empty.

        Args:
            value (Optional[str]): Raw ``hca_id``, ``customer_id`` or
                ``company_id`` value.

        Returns:
            Optional[str]: The identifier, or ``None``.

        Raises:
            MTUserResponseInvalidHcaId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTUserResponseInvalidHcaId(
                f"Invalid identifier: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("must_change_password", mode="before")
    def validate_must_change_password(cls, value: Optional[bool]) -> bool:
        """Validates that ``must_change_password`` is a boolean.

        Args:
            value (Optional[bool]): Raw ``must_change_password`` value.

        Returns:
            bool: The validated flag.

        Raises:
            MTUserResponseInvalidIsActive: If ``value`` is not a boolean.

        Notes:
            Rejected rather than coerced, for the same reason as ``is_active``:
            a truthy string would send a client to the password screen, or past
            it, without anybody having decided so.
        """
        if not isinstance(value, bool):
            raise MTUserResponseInvalidIsActive(
                f"Invalid must_change_password: {value!r}. Must be a boolean."
            )
        return value

    @field_validator("created_at", "updated_at", mode="before")
    def validate_timestamps(
        cls, value: Union[str, datetime, None]
    ) -> Optional[datetime]:
        """Validates that a timestamp is ``None``, a datetime or ISO-8601 text.

        Args:
            value (Union[str, datetime, None]): Raw timestamp value.

        Returns:
            Optional[datetime]: The parsed timestamp, or ``None``.

        Raises:
            MTUserResponseInvalidDate: If ``value`` is neither ``None``, a
                datetime, nor a parseable ISO-8601 string.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise MTUserResponseInvalidDate(
                f"Invalid timestamp: {value!r}. Must be a datetime, an "
                f"ISO-8601 string or None."
            )
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            raise MTUserResponseInvalidDate(
                f"Invalid timestamp: {value!r}. Must be ISO-8601."
            ) from None

    @field_serializer("created_at", "updated_at")
    def serialize_date(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    @classmethod
    def from_user(cls, user: User) -> UserResponse:
        """Build the response from a stored account.

        Args:
            user (User): The account to publish.

        Returns:
            UserResponse: The account, without its password hash.

        Raises:
            MTInvalidUserResponseException: If a field of the account does not
                satisfy this model's validators.
        """
        return cls(
            id=user.id,
            email=str(user.email),
            full_name=user.full_name(),
            role=user.role,
            language=user.language.value,
            is_active=user.is_active,
            hca_id=user.hca_id,
            customer_id=user.customer_id,
            company_id=user.company_id,
            photo_url=str(user.photo_url) if user.photo_url is not None else None,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
