from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.people.hca.exceptions import (
    MTCertificationInvalidCode,
    MTCertificationInvalidExpiresOn,
    MTCertificationInvalidIssuer,
    MTCertificationInvalidName,
    MTCertificationInvalidObtainedOn,
)


class Certification(BaseModel):
    """A qualification held by a Home Care Assistant.

    Attributes:
        CODE_MAX_LENGTH (ClassVar[int]): Longest code accepted, matching the
            catalogue's own limit.
        name (str): Name of the qualification.
        code (Optional[str]): The catalogue entry this qualification is an
            instance of, when it was picked from the catalogue rather than
            typed. ``None`` for a free-text record.
        issuer (Optional[str]): Body that awarded it, when recorded.
        obtained_on (Optional[date]): Date it was awarded.
        expires_on (Optional[date]): Date it lapses, or ``None`` when it does
            not expire.

    Notes:
        - Only ``name`` is required. Certifications are captured from paper
          records of varying completeness, and refusing one because its issue
          date is unknown would push managers to invent a date.
        - ``code`` is **optional, and the free-text name stays**, because the
          catalogue arrived after the records did. A qualification typed before
          the catalogue existed is still a qualification somebody holds; making
          the link mandatory would have meant inventing a catalogue entry for
          every distinct spelling already stored, and getting some of them
          wrong. What the code buys is matching: the planner tests
          :meth:`satisfies`, and only a coded qualification can answer it.
    """

    CODE_MAX_LENGTH: ClassVar[int] = 32

    name: str = Field(description="Name of the qualification.")
    code: Optional[str] = Field(
        default=None,
        description="Catalogue code this qualification instantiates, if any.",
    )
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

    @field_validator("code", mode="before")
    def validate_code(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``code`` is ``None`` or a catalogue key.

        Args:
            value (Optional[str]): Raw ``code`` value.

        Returns:
            Optional[str]: The upper-cased code, or ``None`` for a free-text
            qualification.

        Raises:
            MTCertificationInvalidCode: If ``value`` is neither ``None`` nor a
                string of unaccented letters, digits, hyphens or underscores
                within :attr:`CODE_MAX_LENGTH`.

        Notes:
            - A blank string reads as "not from the catalogue" rather than being
              rejected: a form that submits an empty select must still save.
            - The rule is a copy of
              :meth:`~models.catalog.certification_type.CertificationType.validate_code`
              rather than a call to it. The two models must agree, and the copy
              is deliberate — a shared helper would have to live outside both
              classes, which this codebase does not do, and importing the
              catalogue here would make a person's record depend on the
              catalogue package.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTCertificationInvalidCode(
                f"Invalid code: {value!r}. Must be a string or None."
            )
        normalized = value.strip().upper()
        if not normalized:
            return None
        if len(normalized) > cls.CODE_MAX_LENGTH:
            raise MTCertificationInvalidCode(
                f"Invalid code: {value!r}. Must be at most "
                f"{cls.CODE_MAX_LENGTH} characters."
            )
        if not all(
            (character.isascii() and character.isalnum()) or character in "-_"
            for character in normalized
        ):
            raise MTCertificationInvalidCode(
                f"Invalid code: {value!r}. Must hold only unaccented "
                f"letters, digits, hyphens or underscores."
            )
        return normalized

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

    def satisfies(self, code: str, reference: date) -> bool:
        """Return whether this qualification meets a requirement on a given day.

        Args:
            code (str): The catalogue code the work requires.
            reference (date): The day the work happens.

        Returns:
            bool: ``True`` when this record carries that code and has not
            lapsed by ``reference``.

        Notes:
            - **The date matters, and it is the day of the visit rather than
              today.** A first-aid certificate that lapses on Friday qualifies
              its holder for Thursday's round and not for Monday's, and a plan
              built a fortnight ahead has to get that right — checking against
              the moment the solver runs would either send somebody out
              unqualified or hold back work they can legitimately do.
            - A qualification with no ``code`` satisfies nothing. It is a record
              of something somebody holds, not a claim the agency can match
              against, and treating an untyped name as a match would let a
              spelling decide who is qualified.
        """
        if self.code is None:
            return False
        return self.code == code and not self.is_expired_on(reference)
