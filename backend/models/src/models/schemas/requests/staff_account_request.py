from __future__ import annotations

# Standard library imports
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator

# First-party imports
from models.schemas.exceptions import (
    MTStaffAccountRequestInvalidFullName,
    MTStaffAccountRequestInvalidHcaId,
)


class StaffAccountRequest(BaseModel):
    """The payload an administrator sends to create an assistant's account.

    Attributes:
        hca_id (str): The assistant record the account belongs to.
        email (EmailStr): The sign-in address.
        full_name (str): The display name.
        company_id (Optional[str]): The company the account belongs to.

    Notes:
        **There is no password field, and that is the design.** The temporary
        password is generated server-side and returned once; letting an
        administrator choose it would mean the first credential is one they
        picked, typed into a ticket and probably reused across three new
        starters.

        There is no ``role`` either. This route creates assistant accounts;
        promoting somebody is a separate, administrator-only act with its own
        endpoint, and folding the two together would let a manager mint a
        manager.
    """

    hca_id: str = Field(description="The assistant record the account is for.")
    email: EmailStr = Field(description="The sign-in address.")
    full_name: str = Field(description="The display name.")
    company_id: Optional[str] = Field(
        default=None, description="The company the account belongs to."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("hca_id", mode="before")
    def validate_hca_id(cls, value: Union[str, None]) -> str:
        """Validates that the assistant record is named.

        Args:
            value (Union[str, None]): Raw ``hca_id`` value.

        Returns:
            str: The assistant identifier.

        Raises:
            MTStaffAccountRequestInvalidHcaId: If ``value`` is not a non-empty
                string.

        Notes:
            Required. An assistant account with nothing to point at cannot be
            checked against a planning, so the account model refuses one too —
            this is the outer of the two gates, answering 422 rather than 500.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTStaffAccountRequestInvalidHcaId(
                f"Invalid hca_id: {value!r}. An assistant account must name "
                f"the assistant record it belongs to."
            )
        return value.strip()

    @field_validator("full_name", mode="before")
    def validate_full_name(cls, value: Union[str, None]) -> str:
        """Validates that the display name is a non-empty string.

        Args:
            value (Union[str, None]): Raw ``full_name`` value.

        Returns:
            str: The trimmed name.

        Raises:
            MTStaffAccountRequestInvalidFullName: If ``value`` is not a
                non-empty string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTStaffAccountRequestInvalidFullName(
                f"Invalid full_name: {value!r}. Must be a non-empty string."
            )
        return value.strip()
