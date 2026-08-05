from __future__ import annotations

# Standard library imports
from datetime import date, datetime
from typing import ClassVar, FrozenSet, List, Optional, Union

# Third-party imports
from pydantic import (  # noqa: E501
    BaseModel,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

# First-party imports
from models.people.exceptions import (
    MTDrivingLicenseInvalidCategories,
    MTDrivingLicenseInvalidExpiresOn,
    MTDrivingLicenseInvalidNumber,
    MTDrivingLicenseInvalidObtainedOn,
)


class DrivingLicense(BaseModel):
    """A driving licence held by a Home Care Assistant.

    Attributes:
        KNOWN_CATEGORIES (FrozenSet[str]): The European licence categories the
            model recognises.
        CAR_CATEGORIES (FrozenSet[str]): The subset that permits driving a car,
            which is what the planning layer cares about.
        categories (List[str]): Licence categories held, upper-cased.
        number (Optional[str]): Licence number, when recorded.
        obtained_on (Optional[date]): Date the licence was issued.
        expires_on (Optional[date]): Date it must be renewed, or ``None``.

    Notes:
        Holding a licence changes how the planner routes an assistant: the
        travel matrix is built at driving speed for a licence holder and at
        transit speed for everyone else. An assistant who holds only a
        motorcycle category is not treated as a driver, which is why
        :meth:`can_drive_a_car` asks about categories rather than about mere
        presence of a licence.
    """

    KNOWN_CATEGORIES: ClassVar[FrozenSet[str]] = frozenset(
        {
            "AM",
            "A1",
            "A2",
            "A",
            "B1",
            "B",
            "BE",
            "C1",
            "C1E",
            "C",
            "CE",
            "D1",
            "D1E",
            "D",
            "DE",
        }
    )
    CAR_CATEGORIES: ClassVar[FrozenSet[str]] = frozenset({"B", "B1", "BE"})

    categories: List[str] = Field(
        default_factory=list,
        description="Licence categories held, upper-cased.",
    )
    number: Optional[str] = Field(
        default=None,
        description="Licence number, when recorded.",
    )
    obtained_on: Optional[date] = Field(
        default=None,
        description="Date the licence was issued.",
    )
    expires_on: Optional[date] = Field(
        default=None,
        description="Date the licence must be renewed, or None.",
    )

    @field_validator("categories", mode="before")
    def validate_categories(cls, value: JsonValue) -> List[str]:
        """Validates that ``categories`` is a list of known licence categories.

        Args:
            value (JsonValue): Raw list of categories. ``None`` yields an empty
                list.

        Returns:
            List[str]: The upper-cased, de-duplicated categories, in the order
            first seen.

        Raises:
            MTDrivingLicenseInvalidCategories: If ``value`` is neither ``None``
                nor a list, or if an entry is not a known category.

        Notes:
            De-duplication preserves the order the categories were given in
            rather than sorting, so the stored value still reads the way the
            paper licence does.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTDrivingLicenseInvalidCategories(
                f"Invalid categories: {value!r}. Must be a list or None."
            )
        validated: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTDrivingLicenseInvalidCategories(
                    f"Invalid categories entry: {entry!r}. Must be a non-empty string."
                )
            normalized = entry.strip().upper()
            if normalized not in cls.KNOWN_CATEGORIES:
                raise MTDrivingLicenseInvalidCategories(
                    f"Invalid categories entry: {entry!r}. Must be one of: "
                    f"{', '.join(sorted(cls.KNOWN_CATEGORIES))}."
                )
            if normalized not in validated:
                validated.append(normalized)
        return validated

    @field_validator("number", mode="before")
    def validate_number(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``number`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``number`` value.

        Returns:
            Optional[str]: The stripped licence number, or ``None``.

        Raises:
            MTDrivingLicenseInvalidNumber: If ``value`` is neither ``None`` nor
                a non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTDrivingLicenseInvalidNumber(
                f"Invalid number: {value!r}. Must be a non-empty string or None."
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
            MTDrivingLicenseInvalidObtainedOn: If ``value`` is neither ``None``
                nor a date-like value.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTDrivingLicenseInvalidObtainedOn(
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
            MTDrivingLicenseInvalidExpiresOn: If ``value`` is neither ``None``
                nor a date-like value.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, (str, date)):
            return value
        raise MTDrivingLicenseInvalidExpiresOn(
            f"Invalid expires_on: {value!r}. "
            f"Must be a date, an ISO-8601 string, or None."
        )

    @model_validator(mode="after")
    def check_dates(self) -> DrivingLicense:
        """Ensure the renewal date does not precede the issue date.

        Returns:
            DrivingLicense: ``self`` for chaining.

        Raises:
            MTDrivingLicenseInvalidExpiresOn: If both dates are supplied and
                ``expires_on`` falls before ``obtained_on``.
        """
        if (
            self.obtained_on is not None
            and self.expires_on is not None
            and self.expires_on < self.obtained_on
        ):
            raise MTDrivingLicenseInvalidExpiresOn(
                f"Invalid expires_on: {self.expires_on}. "
                f"Must be on or after obtained_on ({self.obtained_on})."
            )
        return self

    def can_drive_a_car(self) -> bool:
        """Return whether the licence permits driving a car.

        Returns:
            bool: ``True`` when at least one held category is a car category.

        Notes:
            A motorcycle-only licence returns ``False``: the planner would
            otherwise route the assistant at car speed on a vehicle they cannot
            use for the job.
        """
        return any(category in self.CAR_CATEGORIES for category in self.categories)

    def is_expired_on(self, reference: date) -> bool:
        """Return whether the licence has lapsed by a given date.

        Args:
            reference (date): The date to test against.

        Returns:
            bool: ``True`` when ``expires_on`` is set and falls strictly before
            ``reference``. A licence with no recorded expiry never lapses.
        """
        if self.expires_on is None:
            return False
        return self.expires_on < reference
