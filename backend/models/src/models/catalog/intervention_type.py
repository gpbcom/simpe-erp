from __future__ import annotations

# Standard library imports
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar, List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_serializer, field_validator  # noqa: E501

# First-party imports
from models.catalog.exceptions import (
    MTInterventionTypeInvalidCode,
    MTInterventionTypeInvalidDate,
    MTInterventionTypeInvalidDescription,
    MTInterventionTypeInvalidHourlyRate,
    MTInterventionTypeInvalidId,
    MTInterventionTypeInvalidIsActive,
    MTInterventionTypeInvalidName,
    MTInterventionTypeInvalidRequiredCertifications,
    MTInterventionTypeInvalidRequiredSkills,
    MTInterventionTypeInvalidServiceCategory,
)
from models.enums import ServiceCategory


class InterventionType(BaseModel):
    """A kind of care the agency sells, defined by an admin or a manager.

    Attributes:
        MAX_HOURLY_RATE (ClassVar[Decimal]): Upper bound accepted for a rate,
            guarding against a misplaced decimal point.
        id (Optional[str]): Identifier, populated on read from the store.
        name (str): Display name; unique across the catalog.
        code (str): Short stable key, upper-cased.
        description (Optional[str]): Free-text description.
        service_category (ServiceCategory): Whether the service is a necessity
            or a comfort, which fixes its VAT rate.
        base_hourly_rate_ht (Optional[Decimal]): Hourly rate excluding tax for
            this type, or ``None`` to bill the agency-wide default.
        is_active (bool): Whether the type may be put on a new quote.
        required_certification_codes (List[str]): Codes from the certification
            catalogue an assistant must hold before this work may be assigned
            to them. Empty by default.
        required_skill_codes (List[str]): Codes from the skill catalogue an
            assistant must declare before this work may be assigned to them.
            Empty by default.
        created_at (Optional[datetime]): Creation timestamp, set by the store.
        updated_at (Optional[datetime]): Last-update timestamp, set by the
            store.

    Notes:
        - The catalog is data, not code: admins and managers add types at
          runtime, so this is a stored entity rather than an enumeration.
        - ``service_category`` lives here rather than on the quote line because a
          kind of care is structurally one or the other — "aide à la toilette" is
          a necessity, "accompagnement sortie loisirs" a comfort. A type that
          would need both must be split in two, which keeps the VAT rate a
          property of what was sold rather than a per-line choice somebody could
          get wrong.
        - ``base_hourly_rate_ht`` is optional, and ``None`` means "bill the
          agency default". Storing a copy of the default instead would freeze it:
          changing the default rate would then silently miss every type that had
          been created before.
        - Types are retired with ``is_active``, never deleted. A quote issued
          last year still references its type, and removing the row would make
          that quote unreprintable.
        - ``required_certification_codes`` is **empty by default**, so adding
          the field changed nothing about work already sold. A default that
          required something would have made every existing planning run fail
          the moment this shipped, which is a migration failure wearing a
          solver's clothes.
        - The codes are the catalogue *default*, and a
          :class:`~models.quoting.quote_line.QuoteLine` may override them. Which
          qualification a given hour actually needs is occasionally a property
          of the customer rather than of the service — the same reasoning that
          moved ``service_category`` onto the line.
        - ``required_skill_codes`` is a **second, independent list**, not more
          entries in the first. The two catalogues are separate because a
          certification is recorded by a manager and a skill is declared by its
          holder, and the planner reports them as different unplaced reasons —
          "nobody holds DEAES" is a hire, "nobody has declared LEVE-PERSONNE"
          may be somebody who can already do it not having said so. One merged
          list would collapse those into one message and send managers to the
          wrong screen. It defaults to empty for the same reason the
          certification list does: adding the field changed nothing about work
          already sold.
    """

    MAX_HOURLY_RATE: ClassVar[Decimal] = Decimal("10000")

    id: Optional[str] = Field(
        default=None,
        description="Identifier, populated on read from the store.",
    )
    name: str = Field(description="Display name; unique across the catalog.")
    code: str = Field(description="Short stable key, upper-cased.")
    description: Optional[str] = Field(
        default=None,
        description="Free-text description.",
    )
    service_category: ServiceCategory = Field(
        description="Whether the service is a necessity or a comfort.",
    )
    base_hourly_rate_ht: Optional[Decimal] = Field(
        default=None,
        description="Hourly rate excluding tax, or None for the default.",
    )
    is_active: bool = Field(
        default=True,
        description="Whether the type may be put on a new quote.",
    )
    required_certification_codes: List[str] = Field(
        default_factory=list,
        description="Certification codes an assistant must hold to do this work.",
    )
    required_skill_codes: List[str] = Field(
        default_factory=list,
        description="Skill codes an assistant must declare to do this work.",
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="Creation timestamp, set by the store.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Last-update timestamp, set by the store.",
    )

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``id`` is ``None`` or a non-empty string.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            Optional[str]: The identifier, or ``None`` before it is persisted.

        Raises:
            MTInterventionTypeInvalidId: If ``value`` is neither ``None`` nor a
                non-empty string.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionTypeInvalidId(
                f"Invalid id: {value!r}. Must be a non-empty string or None."
            )
        return value.strip()

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that ``name`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            str: The stripped display name.

        Raises:
            MTInterventionTypeInvalidName: If ``value`` is not a non-empty
                string.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionTypeInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("code", mode="before")
    def validate_code(cls, value: Optional[str]) -> str:
        """Validates that ``code`` is a non-empty alphanumeric key.

        Args:
            value (Optional[str]): Raw ``code`` value.

        Returns:
            str: The upper-cased key.

        Raises:
            MTInterventionTypeInvalidCode: If ``value`` is not a non-empty
                string of letters, digits, hyphens or underscores.

        Notes:
            Upper-cased and character-restricted so the key stays usable as a
            stable reference in exports and in a URL, where a code carrying
            spaces or accents would have to be escaped differently by every
            consumer.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionTypeInvalidCode(
                f"Invalid code: {value!r}. Must be a non-empty string."
            )
        normalized = value.strip().upper()
        if not all(
            character.isalnum() or character in "-_"
            for character in normalized  # noqa: E501
        ):
            raise MTInterventionTypeInvalidCode(
                f"Invalid code: {value!r}. Must hold only letters, digits, "
                f"hyphens or underscores."
            )
        return normalized

    @field_validator("description", mode="before")
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``description`` is ``None`` or a string.

        Args:
            value (Optional[str]): Raw ``description`` value.

        Returns:
            Optional[str]: The stripped description, or ``None`` when blank.

        Raises:
            MTInterventionTypeInvalidDescription: If ``value`` is neither
                ``None`` nor a string.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTInterventionTypeInvalidDescription(
                f"Invalid description: {value!r}. Must be a string or None."
            )
        stripped = value.strip()
        return stripped if stripped else None

    @field_validator("service_category", mode="before")
    def validate_service_category(
        cls, value: Union[str, ServiceCategory, None]
    ) -> ServiceCategory:
        """Validates that ``service_category`` is a known category.

        Args:
            value (Union[str, ServiceCategory, None]): Raw category value.

        Returns:
            ServiceCategory: The coerced category.

        Raises:
            MTInterventionTypeInvalidServiceCategory: If ``value`` is not a
                known service category.

        Notes:
            There is no default. The category fixes the VAT rate, and guessing
            it would mean quietly charging 5.5% or 20% on somebody's say-so.
        """
        if isinstance(value, ServiceCategory):
            return value
        try:
            return ServiceCategory(value)
        except ValueError:
            raise MTInterventionTypeInvalidServiceCategory(
                f"Invalid service_category: {value!r}. Must be one of: "
                f"{', '.join(ServiceCategory.values())}."
            ) from None

    @field_validator("base_hourly_rate_ht", mode="before")
    def validate_base_hourly_rate_ht(
        cls, value: Union[int, float, str, Decimal, None]
    ) -> Optional[Decimal]:
        """Validates that ``base_hourly_rate_ht`` is ``None`` or positive.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw rate value.

        Returns:
            Optional[Decimal]: The rate as a :class:`~decimal.Decimal`, or
            ``None`` to bill the agency default.

        Raises:
            MTInterventionTypeInvalidHourlyRate: If ``value`` cannot be read as
                a decimal, is not strictly positive, or exceeds
                :attr:`MAX_HOURLY_RATE`.

        Notes:
            Routed through ``str`` before reaching :class:`~decimal.Decimal`,
            so a JSON float such as ``31.905`` keeps its exact value instead of
            picking up the binary approximation.
        """
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTInterventionTypeInvalidHourlyRate(
                f"Invalid base_hourly_rate_ht: {value!r}. "
                f"Must be a positive decimal amount or None."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTInterventionTypeInvalidHourlyRate(
                f"Invalid base_hourly_rate_ht: {value!r}. "
                f"Must be a positive decimal amount or None."
            ) from None
        if not coerced.is_finite() or coerced <= 0:
            raise MTInterventionTypeInvalidHourlyRate(
                f"Invalid base_hourly_rate_ht: {coerced!r}. "  # noqa: E501
                "Must be strictly positive."
            )
        if coerced > cls.MAX_HOURLY_RATE:
            raise MTInterventionTypeInvalidHourlyRate(
                f"Invalid base_hourly_rate_ht: {coerced!r}. "
                f"Must be at most {cls.MAX_HOURLY_RATE}."
            )
        return coerced

    @field_validator("is_active", mode="before")
    def validate_is_active(cls, value: Union[bool, str, int, None]) -> bool:
        """Validates that ``is_active`` is a boolean.

        Args:
            value (Union[bool, str, int, None]): Raw ``is_active`` value.
                ``None`` falls back to ``True``.

        Returns:
            bool: The validated flag.

        Raises:
            MTInterventionTypeInvalidIsActive: If ``value`` is neither ``None``
                nor a boolean.
        """
        if value is None:
            return True
        if not isinstance(value, bool):
            raise MTInterventionTypeInvalidIsActive(
                f"Invalid is_active: {value!r}. Must be true or false."
            )
        return value

    @field_validator("required_certification_codes", mode="before")
    def validate_required_certification_codes(cls, value: JsonValue) -> List[str]:  # noqa: E501
        """Validates that the required codes are a list of catalogue keys.

        Args:
            value (JsonValue): Raw ``required_certification_codes`` value.
                ``None`` falls back to an empty list.

        Returns:
            List[str]: The upper-cased codes, de-duplicated, in the order they
            were given.

        Raises:
            MTInterventionTypeInvalidRequiredCertifications: If ``value`` is
                neither ``None`` nor a list of non-empty strings.

        Notes:
            - De-duplicated rather than refused on a repeat. The same code
              listed twice means exactly what it means once, and rejecting it
              would fail a save over something the screen can silently fix.
            - Upper-cased here so a requirement matches an assistant's
              qualification by plain equality. Normalising at comparison time
              instead would put the rule in the solver's hot loop and let it
              drift from the one applied on the way in.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTInterventionTypeInvalidRequiredCertifications(
                f"Invalid required_certification_codes: {value!r}. "
                f"Must be a list of certification codes."
            )
        codes: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTInterventionTypeInvalidRequiredCertifications(
                    f"Invalid certification code: {entry!r}. "
                    f"Must be a non-empty string."
                )
            normalized = entry.strip().upper()
            if normalized not in codes:
                codes.append(normalized)
        return codes

    @field_validator("required_skill_codes", mode="before")
    def validate_required_skill_codes(cls, value: JsonValue) -> List[str]:
        """Validates that the required skill codes are a list of catalogue keys.

        Args:
            value (JsonValue): Raw ``required_skill_codes`` value. ``None``
                falls back to an empty list.

        Returns:
            List[str]: The upper-cased codes, de-duplicated, in the order they
            were given.

        Raises:
            MTInterventionTypeInvalidRequiredSkills: If ``value`` is neither
                ``None`` nor a list of non-empty strings.

        Notes:
            The rule is the same as
            :meth:`validate_required_certification_codes` and the exception is
            not. A message naming the wrong catalogue sends whoever reads it to
            the wrong screen, and the two are edited by different people.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTInterventionTypeInvalidRequiredSkills(
                f"Invalid required_skill_codes: {value!r}. "
                f"Must be a list of skill codes."
            )
        codes: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTInterventionTypeInvalidRequiredSkills(
                    f"Invalid skill code: {entry!r}. Must be a non-empty string."
                )
            normalized = entry.strip().upper()
            if normalized not in codes:
                codes.append(normalized)
        return codes

    @field_validator("created_at", "updated_at", mode="before")
    def validate_date(
        cls, value: Union[str, datetime, None]
    ) -> Union[str, datetime, None]:
        """Validates that a timestamp is a datetime, an ISO string or ``None``.

        Args:
            value (Union[str, datetime, None]): Raw timestamp value.

        Returns:
            Union[str, datetime, None]: The value handed back for Pydantic to
            parse.

        Raises:
            MTInterventionTypeInvalidDate: If ``value`` is neither ``None`` nor
                a datetime-like value.
        """
        if value is None or isinstance(value, (str, datetime)):
            return value
        raise MTInterventionTypeInvalidDate(
            f"Invalid timestamp: {value!r}. "
            f"Must be a datetime, an ISO-8601 string, or None."
        )

    @field_serializer("created_at", "updated_at")
    def serialize_date(self, value: Optional[datetime]) -> Optional[str]:
        """Serialize a timestamp to an ISO-8601 string.

        Args:
            value (Optional[datetime]): The timestamp to serialize.

        Returns:
            Optional[str]: The ISO-8601 representation, or ``None``.
        """
        return value.isoformat() if value is not None else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def vat_rate(self) -> Decimal:
        """Return the VAT rate this type is billed at.

        Returns:
            Decimal: ``0.055`` for a necessity service, ``0.20`` for a comfort
            one.
        """
        return self.service_category.vat_rate()

    def effective_hourly_rate_ht(self, default_rate: Decimal) -> Decimal:
        """Return the hourly rate this type bills at, before any surcharge.

        Args:
            default_rate (Decimal): The agency-wide rate, used when this type
                sets none of its own.

        Returns:
            Decimal: This type's rate, or ``default_rate``.

        Notes:
            Resolving the fallback here rather than at each call site is what
            makes "no rate means the default" a property of the type instead of
            something every caller has to remember.
        """
        if self.base_hourly_rate_ht is None:
            return default_rate
        return self.base_hourly_rate_ht
