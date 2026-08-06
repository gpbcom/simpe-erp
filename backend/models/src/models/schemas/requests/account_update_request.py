from __future__ import annotations

# Standard library imports
from typing import Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTAccountUpdateRequestInvalidEmail,
    MTAccountUpdateRequestInvalidFullName,
)


class AccountUpdateRequest(BaseModel):
    """The payload changing what an account holder owns about their account.

    Attributes:
        full_name (str): The display name to show.
        email (EmailStr): The address to sign in with from now on.

    Notes:
        **The shape of this model is the permission.** Every other column on an
        account is either somebody else's to set or the system's own record of
        what happened, and none of them can be reached from here:

        - ``role`` is an administrator's act, performed on the accounts screen
          through ``POST /api/v1/users/{id}/promote``. A payload that could
          carry a role would be a payload that lets any holder grant themselves
          one, and a self-service route is exactly where that would be tried.
        - ``is_active`` is an administrator's too. Accepting it here would let
          somebody lock themselves out of the only screen that could undo it.
        - ``hca_id`` binds an account to an assistant record. Rebinding it would
          hand the holder somebody else's customers and planning.
        - ``company_id`` decides which agency's data the account can see at all.
        - ``hashed_password`` has its own route, which demands the current
          password first — a token left on a shared machine is precisely when
          somebody else would change it.
        - ``must_change_password``, ``password_changed_at``, ``created_at`` and
          ``updated_at`` are records of what happened rather than settings.

        Leaving them off the model rather than checking for them means there is
        no check to forget, and no second copy of the rule to drift.

        Both fields are required rather than optional. A partial payload would
        make "clear my display name" and "leave my display name alone"
        indistinguishable, and the screen holds both values already.
    """

    full_name: str = Field(description="The display name to show.")
    email: EmailStr = Field(description="The address to sign in with.")

    @field_validator("full_name", mode="before")
    def validate_full_name(cls, value: Union[str, None]) -> str:
        """Validates that ``full_name`` is a non-empty name.

        Args:
            value (Union[str, None]): Raw ``full_name`` value.

        Returns:
            str: The stripped display name.

        Raises:
            MTAccountUpdateRequestInvalidFullName: If ``value`` is missing or
                blank once stripped.

        Notes:
            Stripped before it is judged, so a name of spaces is refused rather
            than stored. It is what a manager reads beside every quote this
            account writes, and a blank one there is a quote from nobody.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAccountUpdateRequestInvalidFullName(
                f"Invalid full_name: {value!r}. Must be a non-empty name."
            )
        return value.strip()

    @field_validator("email", mode="before")
    def validate_email(cls, value: Union[str, None]) -> str:
        """Validates that ``email`` is present before it is parsed.

        Args:
            value (Union[str, None]): Raw ``email`` value.

        Returns:
            str: The stripped, lower-cased address.

        Raises:
            MTAccountUpdateRequestInvalidEmail: If ``value`` is missing or
                blank once stripped.

        Notes:
            Lower-cased here rather than left to the address parser. This is
            the value the account signs in with, and addresses are looked up
            exactly, so ``Luc.Martin@`` saved from the account screen would
            leave the holder unable to sign in with what they typed yesterday.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTAccountUpdateRequestInvalidEmail(
                f"Invalid email: {value!r}. Must be a non-empty address."
            )
        return value.strip().lower()
