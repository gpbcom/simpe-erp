from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import UserRole
from models.schemas.exceptions import MTRoleUpdateRequestInvalidRole


class RoleUpdateRequest(BaseModel):
    """The payload changing an account's role.

    Attributes:
        role (UserRole): The role to grant.

    Notes:
        The model carries exactly one field. That is the enforcement of "an
        administrator promotes an account" — there is no reachable route that
        would let a role change ride along with an unrelated edit.
    """

    role: UserRole = Field(description="The role to grant.")

    @field_validator("role", mode="before")
    def validate_role(cls, value: Union[str, UserRole, None]) -> UserRole:
        """Validates that ``role`` is a known user role.

        Args:
            value (Union[str, UserRole, None]): Raw ``role`` value.

        Returns:
            UserRole: The coerced role.

        Raises:
            MTRoleUpdateRequestInvalidRole: If ``value`` is not a known role.

        Notes:
            There is no default. A promotion must state the role it grants;
            defaulting would let an empty body silently change an account.
        """
        if isinstance(value, UserRole):
            return value
        try:
            return UserRole(value)
        except ValueError:
            raise MTRoleUpdateRequestInvalidRole(
                f"Invalid role: {value!r}. Must be one of: "
                f"{', '.join(UserRole.values())}."
            ) from None
