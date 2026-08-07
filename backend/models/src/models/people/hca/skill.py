from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import ClassVar, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator, model_validator

# First-party imports
from models.people.hca.exceptions import (
    MTSkillInvalidCode,
    MTSkillInvalidExpiresOn,
    MTSkillInvalidId,
    MTSkillInvalidIssuer,
    MTSkillInvalidName,
    MTSkillInvalidObtainedOn,
)


class Skill(BaseModel):
    """A skill a Home Care Assistant declares about themselves.

    Attributes:
        CODE_MAX_LENGTH (ClassVar[int]): Longest code accepted, matching the
            catalogue's own limit.
        id (Optional[str]): Identifier, populated on read from the store.
        name (str): Name of the skill.
        code (Optional[str]): The catalogue entry this skill is an instance of,
            when it was picked from the catalogue rather than typed. ``None``
            for a free-text record.
        issuer (Optional[str]): Who attested it — a training body, a former
            employer — when there is one.
        obtained_on (Optional[date]): Date it was acquired.
        expires_on (Optional[date]): Date it lapses, or ``None`` when it does
            not.

    Notes:
        - **The shape mirrors
          :class:`~models.people.hca.certification.Certification` exactly, with
          one addition: ``id``.** A certification is replaced wholesale by the
          employment form — a manager sends the list the assistant now holds —
          so no individual row ever needs addressing. A skill is added one at a
          time by its owner and removed one at a time by its owner, a manager
          or an administrator, and every one of those operations names a single
          record. Without an identifier the only way to delete one would be to
          match on its fields, which cannot distinguish two skills somebody
          entered under the same name.
        - There is deliberately **no ``hca_id``**. The owning assistant comes
          from the route and is applied by the repository, so a payload cannot
          file a skill against a colleague — the hazard
          :meth:`~storage.mappers.people.hca_mapper.HcaMapper._availability_rows`
          has to log a warning about, avoided here by not having the field at
          all.
        - Only ``name`` is required. A skill is self-declared, and refusing one
          because its date is unknown would push people to invent a date or to
          not declare the skill — and an undeclared skill is a visit nobody
          gets assigned to.
        - ``code`` is **optional, and the free-text name stays**. What the code
          buys is matching: the planner tests :meth:`satisfies`, and only a
          coded skill can answer it. A free-text one is a record of something
          somebody can do, which is worth keeping even though the solver cannot
          act on it.
    """

    CODE_MAX_LENGTH: ClassVar[int] = 32

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    name: str = Field(description="Name of the skill.")
    code: Optional[str] = Field(
        default=None,
        description="Catalogue code this skill instantiates, if any.",
    )
    issuer: Optional[str] = Field(
        default=None,
        description="Who attested the skill.",
    )
    obtained_on: Optional[date] = Field(
        default=None,
        description="Date the skill was acquired.",
    )
    expires_on: Optional[date] = Field(
        default=None,
        description="Date the skill lapses, or None if it does not.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is persisted.

        Raises:
            MTSkillInvalidId: If ``value`` is neither ``None`` nor a non-empty
                string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTSkillInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The stripped skill name.

        Raises:
            MTSkillInvalidName: If ``value`` is not a string, or is empty once
                stripped.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTSkillInvalidName(
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
            skill.

        Raises:
            MTSkillInvalidCode: If ``value`` is neither ``None`` nor a string
                of unaccented letters, digits, hyphens or underscores within
                :attr:`CODE_MAX_LENGTH`.

        Notes:
            - A blank string reads as "not from the catalogue" rather than
              being rejected: a form that submits an empty select must still
              save, and the self-service form offers exactly that.
            - The rule is a copy of
              :meth:`~models.catalog.skill_type.SkillType.validate_code` rather
              than a call to it. The two models must agree, and the copy is
              deliberate — a shared helper would have to live outside both
              classes, which this codebase does not do, and importing the
              catalogue here would make a person's record depend on the
              catalogue package.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTSkillInvalidCode(
                f"Invalid code: {value!r}. Must be a string or None."
            )
        normalized = value.strip().upper()
        if not normalized:
            return None
        if len(normalized) > cls.CODE_MAX_LENGTH:
            raise MTSkillInvalidCode(
                f"Invalid code: {value!r}. Must be at most "
                f"{cls.CODE_MAX_LENGTH} characters."
            )
        if not all(
            (character.isascii() and character.isalnum()) or character in "-_"
            for character in normalized
        ):
            raise MTSkillInvalidCode(
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
            MTSkillInvalidIssuer: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTSkillInvalidIssuer(
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
            MTSkillInvalidObtainedOn: If ``value`` is neither ``None`` nor a
                date-like value.

        Notes:
            A :class:`~datetime.datetime` is narrowed to its date part rather
            than rejected: a date picker that submits midnight in the browser's
            timezone is the honest case, not a malformed request.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTSkillInvalidObtainedOn(
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
            MTSkillInvalidExpiresOn: If ``value`` is neither ``None`` nor a
                date-like value.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTSkillInvalidExpiresOn(
            f"Invalid expires_on: {value!r}. "
            f"Must be a date, an ISO-8601 string, or None."
        )

    @model_validator(mode="after")
    def check_dates(self) -> Skill:
        """Ensure the expiry date does not precede the acquisition date.

        Returns:
            Skill: ``self`` for chaining.

        Raises:
            MTSkillInvalidExpiresOn: If both dates are supplied and
                ``expires_on`` falls before ``obtained_on``.
        """
        if (
            self.obtained_on is not None
            and self.expires_on is not None
            and self.expires_on < self.obtained_on
        ):
            raise MTSkillInvalidExpiresOn(
                f"Invalid expires_on: {self.expires_on}. "
                f"Must be on or after obtained_on ({self.obtained_on})."
            )
        return self

    def is_expired_on(self, reference: date) -> bool:
        """Return whether the skill has lapsed by a given date.

        Args:
            reference (date): The date to test against.

        Returns:
            bool: ``True`` when ``expires_on`` is set and falls strictly before
            ``reference``. A skill with no expiry never lapses.
        """
        if self.expires_on is None:
            return False
        return self.expires_on < reference

    def satisfies(self, code: str, reference: date) -> bool:
        """Return whether this skill meets a requirement on a given day.

        Args:
            code (str): The catalogue code the work requires.
            reference (date): The day the work happens.

        Returns:
            bool: ``True`` when this record carries that code and has not
            lapsed by ``reference``.

        Notes:
            - **The date matters, and it is the day of the visit rather than
              today.** A skill whose refresher lapses on Friday qualifies its
              holder for Thursday's round and not for Monday's, and a plan
              built a fortnight ahead has to get that right — checking against
              the moment the solver runs would either send somebody out
              unqualified or hold back work they can legitimately do.
            - A skill with no ``code`` satisfies nothing. It is a record of
              something somebody can do, not a claim the agency can match
              against, and treating an untyped name as a match would let a
              spelling decide who is qualified.
        """
        if self.code is None:
            return False
        return self.code == code and not self.is_expired_on(reference)
