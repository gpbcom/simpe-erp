from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.people.exceptions import (
    MTCertificationInvalidExpiresOn,
    MTCertificationInvalidIssuer,
    MTCertificationInvalidName,
    MTCertificationInvalidObtainedOn,
)


class Certification(BaseModel):
    """A qualification held by a Home Care Assistant.

    Attributes:
        name (str): Name of the qualification.
        issuer (Optional[str]): Body that awarded it, when recorded.
        obtained_on (Optional[date]): Date it was awarded.
        expires_on (Optional[date]): Date it lapses, or ``None`` when it does
            not expire.

    Notes:
        Only ``name`` is required. Certifications are captured from paper
        records of varying completeness, and refusing one because its issue
        date is unknown would push managers to invent a date.
    """

    name: str = Field(description="Name of the qualification.")
    issuer: Optional[str] = Field(
        default=None,
        description="Body that awarded the qualification.",
    )
    obtained_on: Optional[date] = Field(
        default=None,
        description="Date the qualification was awarded.",
    )
    expires_on: Optional[date] = Field(
        default=None,
        description="Date the qualification lapses, or None if it does not.",
    )

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The stripped qualification name.

        Raises:
            MTCertificationInvalidName: If ``value`` is not a string, or is
                empty once stripped.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTCertificationInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("issuer", mode="before")
    def validate_issuer(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``issuer`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``issuer`` value.

        Returns:
            Optional[str]: The stripped issuer name, or ``None``.

        Raises:
            MTCertificationInvalidIssuer: If ``value`` is neither ``None`` nor
                a non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTCertificationInvalidIssuer(
                f"Invalid issuer: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("obtained_on", mode="before")
    def validate_obtained_on(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date, None]:
        """Validates that ``obtained_on`` is a date, an ISO string or ``None``.

        Args:
            value (Union[str, date, datetime, None]): Raw ``obtained_on`` value.

        Returns:
            Union[str, date, None]: The value handed back for Pydantic to parse.

        Raises:
            MTCertificationInvalidObtainedOn: If ``value`` is neither ``None``
                nor a date-like value.

        Notes:
            A :class:`~datetime.datetime` is narrowed to its date part rather
            than rejected: the source records sometimes carry a midnight
            timestamp where a plain date was meant.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTCertificationInvalidObtainedOn(
            f"Invalid obtained_on: {value!r}. "
            f"Must be a date, an ISO-8601 string, or None."
        )

    @field_validator("expires_on", mode="before")
    def validate_expires_on(
        cls, value: Union[str, date, datetime, None]
    ) -> Union[str, date, None]:
        """Validates that ``expires_on`` is a date, an ISO string or ``None``.

        Args:
            value (Union[str, date, datetime, None]): Raw ``expires_on`` value.

        Returns:
            Union[str, date, None]: The value handed back for Pydantic to parse.

        Raises:
            MTCertificationInvalidExpiresOn: If ``value`` is neither ``None``
                nor a date-like value.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTCertificationInvalidExpiresOn(
            f"Invalid expires_on: {value!r}. "
            f"Must be a date, an ISO-8601 string, or None."
        )

    @model_validator(mode="after")
    def check_dates(self) -> Certification:
        """Ensure the expiry date does not precede the award date.

        Returns:
            Certification: ``self`` for chaining.

        Raises:
            MTCertificationInvalidExpiresOn: If both dates are supplied and
                ``expires_on`` falls before ``obtained_on``.
        """
        if (
            self.obtained_on is not None
            and self.expires_on is not None
            and self.expires_on < self.obtained_on
        ):
            raise MTCertificationInvalidExpiresOn(
                f"Invalid expires_on: {self.expires_on}. "
                f"Must be on or after obtained_on ({self.obtained_on})."
            )
        return self

    def is_expired_on(self, reference: date) -> bool:
        """Return whether the qualification has lapsed by a given date.

        Args:
            reference (date): The date to test against.

        Returns:
            bool: ``True`` when ``expires_on`` is set and falls strictly before
            ``reference``. A qualification with no expiry never lapses.
        """
        if self.expires_on is None:
            return False
        return self.expires_on < reference
