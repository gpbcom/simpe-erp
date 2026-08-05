from __future__ import annotations

# Standard library imports
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_extra_types.phone_numbers import PhoneNumber

# First-party imports
from models.enums import ContractType
from models.geo.postal_address import PostalAddress
from models.schemas.exceptions import (
    MTHcaApplicationRequestInvalidCompany,
    MTHcaApplicationRequestInvalidName,
    MTHcaApplicationRequestInvalidPassword,
)


class HcaApplicationRequest(BaseModel):
    """The payload an assistant submits to apply to a company.

    Attributes:
        MIN_PASSWORD_LENGTH (ClassVar[int]): Shortest password accepted.
        MAX_PASSWORD_BYTES (ClassVar[int]): Longest password accepted, matching
            what bcrypt actually reads.
        company_id (str): The company being applied to.
        first_name (str): Given name.
        last_name (str): Family name.
        phone_number (PhoneNumber): Contact telephone number.
        email (EmailStr): The address that becomes the sign-in on approval.
        password (str): The password chosen by the applicant.
        address (PostalAddress): Where the applicant lives.
        contract_type (Optional[ContractType]): The contract hoped for.

    Notes:
        Submitted **without a credential** — the applicant does not have one
        yet. What that costs is stated plainly: this endpoint accepts input
        from anybody, so every field is validated here rather than trusted, and
        approval is a human decision rather than a formality.

        The password bounds match those on registration. bcrypt silently
        ignores anything past 72 bytes, so a longer password would appear to be
        accepted while only its first 72 bytes ever mattered.

        There is no ``role`` field. An application produces an assistant
        account and nothing else; a role in the payload would be an unauthenticated
        caller asking to be an administrator.
    """

    MIN_PASSWORD_LENGTH: ClassVar[int] = 12
    MAX_PASSWORD_BYTES: ClassVar[int] = 72

    company_id: str = Field(description="The company being applied to.")
    first_name: str = Field(description="Given name.")
    last_name: str = Field(description="Family name.")
    phone_number: PhoneNumber = Field(description="Contact telephone number.")
    email: EmailStr = Field(description="The address that becomes the sign-in.")
    password: str = Field(description="The password chosen by the applicant.")
    address: PostalAddress = Field(description="Where the applicant lives.")
    contract_type: Optional[ContractType] = Field(
        default=None, description="The contract hoped for."
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("company_id", mode="before")
    def validate_company_id(cls, value: Union[str, None]) -> str:
        """Validates that a company was chosen.

        Args:
            value (Union[str, None]): Raw ``company_id`` value.

        Returns:
            str: The company identifier.

        Raises:
            MTHcaApplicationRequestInvalidCompany: If ``value`` is not a
                non-empty string.

        Notes:
            The specification requires the applicant to choose which company
            they are registering with, so there is no default: an application
            addressed to nobody has nobody able to decide it.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaApplicationRequestInvalidCompany(
                f"Invalid company_id: {value!r}. You must choose the company "
                f"you are applying to."
            )
        return value.strip()

    @field_validator("first_name", "last_name", mode="before")
    def validate_names(cls, value: Union[str, None]) -> str:
        """Validates that a name is a non-empty string.

        Args:
            value (Union[str, None]): Raw name value.

        Returns:
            str: The trimmed name.

        Raises:
            MTHcaApplicationRequestInvalidName: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTHcaApplicationRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("password", mode="before")
    def validate_password(cls, value: Union[str, None]) -> str:
        """Validates that the chosen password is within the accepted range.

        Args:
            value (Union[str, None]): Raw ``password`` value.

        Returns:
            str: The password, unmodified.

        Raises:
            MTHcaApplicationRequestInvalidPassword: If ``value`` is not a
                string of an accepted length.

        Notes:
            Never stripped, and never echoed into an error message. One would
            change the stored credential; the other would put it in the logs.
        """
        if not isinstance(value, str):
            raise MTHcaApplicationRequestInvalidPassword(
                "Invalid password. Must be a string."
            )
        if len(value) < cls.MIN_PASSWORD_LENGTH:
            raise MTHcaApplicationRequestInvalidPassword(
                f"Invalid password. Must be at least "
                f"{cls.MIN_PASSWORD_LENGTH} characters."
            )
        if len(value.encode("utf-8")) > cls.MAX_PASSWORD_BYTES:
            raise MTHcaApplicationRequestInvalidPassword(
                f"Invalid password. Must be at most {cls.MAX_PASSWORD_BYTES} "
                f"bytes once encoded; anything beyond that is silently ignored."
            )
        return value
