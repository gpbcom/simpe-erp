from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTPasswordChangeRequestInvalidCurrent,
    MTPasswordChangeRequestInvalidNew,
)


class PasswordChangeRequest(BaseModel):
    """The payload replacing an account's own password.

    Attributes:
        MIN_PASSWORD_LENGTH (ClassVar[int]): Shortest password accepted.
        MAX_PASSWORD_BYTES (ClassVar[int]): Longest password accepted, matching
            what bcrypt actually reads.
        current_password (str): The password being replaced.
        new_password (str): The password to set.

    Notes:
        The current password is required even though the caller is already
        authenticated. A token left on a shared machine is exactly the case
        where somebody else would change the password, and knowing the old one
        is what tells the holder apart from whoever found the session.

        Neither value is stripped or echoed. Stripping would change the
        credential; echoing would put it in a log.
    """

    MIN_PASSWORD_LENGTH: ClassVar[int] = 12
    MAX_PASSWORD_BYTES: ClassVar[int] = 72

    current_password: str = Field(description="The password being replaced.")
    new_password: str = Field(description="The password to set.")

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("current_password", mode="before")
    def validate_current_password(cls, value: Optional[str]) -> str:
        """Validates that the current password was supplied.

        Args:
            value (Optional[str]): Raw ``current_password`` value.

        Returns:
            str: The password, unmodified.

        Raises:
            MTPasswordChangeRequestInvalidCurrent: If ``value`` is not a
                non-empty string.

        Notes:
            Only presence is checked, not length. The old password was accepted
            under whatever policy applied when it was set, and rejecting it
            here for being short would lock out exactly the accounts most in
            need of changing it.
        """
        if not isinstance(value, str) or not value:
            raise MTPasswordChangeRequestInvalidCurrent(
                "Invalid current_password. Must be supplied."
            )
        return value

    @field_validator("new_password", mode="before")
    def validate_new_password(cls, value: Optional[str]) -> str:
        """Validates that the new password meets the policy.

        Args:
            value (Optional[str]): Raw ``new_password`` value.

        Returns:
            str: The password, unmodified.

        Raises:
            MTPasswordChangeRequestInvalidNew: If ``value`` is not a string of
                an accepted length.
        """
        if not isinstance(value, str):
            raise MTPasswordChangeRequestInvalidNew(
                "Invalid new_password. Must be a string."
            )
        if len(value) < cls.MIN_PASSWORD_LENGTH:
            raise MTPasswordChangeRequestInvalidNew(
                f"Invalid new_password. Must be at least "
                f"{cls.MIN_PASSWORD_LENGTH} characters."
            )
        if len(value.encode("utf-8")) > cls.MAX_PASSWORD_BYTES:
            raise MTPasswordChangeRequestInvalidNew(
                f"Invalid new_password. Must be at most "
                f"{cls.MAX_PASSWORD_BYTES} bytes once encoded. Anything beyond "
                f"that is silently ignored."
            )
        return value
