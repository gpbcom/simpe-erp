from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import List, Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.enums import ServiceCategory
from models.schemas.exceptions import (
    MTInterventionTypeUpdateRequestInvalidCertifications,
    MTInterventionTypeUpdateRequestInvalidName,
    MTInterventionTypeUpdateRequestInvalidRate,
    MTInterventionTypeUpdateRequestInvalidSkills,
)


class InterventionTypeUpdateRequest(BaseModel):
    """The payload changing what a catalogue entry is called, costs and covers.

    Attributes:
        name (Optional[str]): The display name.
        description (Optional[str]): What the service is.
        service_category (Optional[ServiceCategory]): Which VAT rate applies.
        base_hourly_rate_ht (Optional[Decimal]): The rate this entry bills at,
            or ``None`` to bill at the agency rate.
        is_active (Optional[bool]): Whether the service may still be sold.
        required_certification_codes (Optional[List[str]]): The qualifications
            an assistant must hold to deliver this service.
        required_skill_codes (Optional[List[str]]): The skills an assistant
            must declare to deliver this service.

    Notes:
        **Every field is optional, and that is what makes this a PATCH.** The
        route was declared ``PATCH`` but took a whole
        :class:`~models.catalog.intervention_type.InterventionType`, so a
        request that changed one field had to resend all of them — and one that
        did not was answered ``422: code Field required``. A verb that says
        "change part of this" and a payload that means "replace all of it" is a
        contradiction the caller pays for.

        **``code`` is absent, so it cannot be changed at all.** It is the stable
        key every quote line ever written against this entry refers to;
        renaming it would leave a quote from last month naming a service the
        catalogue no longer has. The screen shows the field locked, but the
        rule lives here — a locked input is a courtesy, not a control.

        **A field left out and a field set to ``None`` are different requests.**
        Clearing ``base_hourly_rate_ht`` means "bill at the agency rate", which
        is a real and useful state; omitting it means "leave the rate alone".
        Optional fields alone cannot tell those apart, so the route reads
        ``model_dump(exclude_unset=True)`` and applies only what was actually
        sent. Without that, saving a name change would silently reset the rate.
    """

    name: Optional[str] = Field(default=None, description="The display name.")
    description: Optional[str] = Field(default=None, description="What the service is.")
    service_category: Optional[ServiceCategory] = Field(
        default=None, description="Which VAT rate applies."
    )
    base_hourly_rate_ht: Optional[Decimal] = Field(
        default=None, description="The rate this entry bills at, or None."
    )
    is_active: Optional[bool] = Field(
        default=None, description="Whether the service may still be sold."
    )
    required_certification_codes: Optional[List[str]] = Field(
        default=None,
        description="Qualifications required to deliver this service.",
    )
    required_skill_codes: Optional[List[str]] = Field(
        default=None,
        description="Skills required to deliver this service.",
    )

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``name`` is absent or a non-empty display name.

        Args:
            value (Optional[str]): Raw ``name`` value.

        Returns:
            Optional[str]: The stripped name, or ``None`` when not sent.

        Raises:
            MTInterventionTypeUpdateRequestInvalidName: If ``value`` is present
                but blank once stripped, or is not a string.

        Notes:
            ``None`` passes because it means "not sent". A blank string does
            not: the name is what an operator picks from when writing a quote
            and what the customer reads on the printed one, so an entry with no
            name is one nobody can sell and nobody can read.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTInterventionTypeUpdateRequestInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty display name."
            )
        return value.strip()

    @field_validator("required_certification_codes", mode="before")
    def validate_required_certification_codes(
        cls, value: JsonValue
    ) -> Optional[List[str]]:
        """Validates that the required codes are absent or a list of keys.

        Args:
            value (JsonValue): Raw ``required_certification_codes`` value.

        Returns:
            Optional[List[str]]: The upper-cased codes, de-duplicated, or
            ``None`` when the field was not sent.

        Raises:
            MTInterventionTypeUpdateRequestInvalidCertifications: If ``value``
                is neither ``None`` nor a list of non-empty strings.

        Notes:
            ``None`` means "not sent" and an **empty list** means "require
            nothing from now on" — the same distinction the rate already
            relies on, and the reason the route reads
            ``model_dump(exclude_unset=True)``. Collapsing the two would make
            it impossible to lift a requirement once one had been set, which is
            the edit somebody makes after discovering the requirement was
            wrong.
        """
        if value is None:
            return None
        if not isinstance(value, list):
            raise MTInterventionTypeUpdateRequestInvalidCertifications(
                f"Invalid required_certification_codes: {value!r}. "
                f"Must be a list of certification codes."
            )
        codes: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTInterventionTypeUpdateRequestInvalidCertifications(
                    f"Invalid certification code: {entry!r}. "
                    f"Must be a non-empty string."
                )
            normalized = entry.strip().upper()
            if normalized not in codes:
                codes.append(normalized)
        return codes

    @field_validator("required_skill_codes", mode="before")
    def validate_required_skill_codes(cls, value: JsonValue) -> Optional[List[str]]:
        """Validates that the required skills are absent or a list of keys.

        Args:
            value (JsonValue): Raw ``required_skill_codes`` value.

        Returns:
            Optional[List[str]]: The upper-cased codes, de-duplicated, or
            ``None`` when the field was not sent.

        Raises:
            MTInterventionTypeUpdateRequestInvalidSkills: If ``value`` is
                neither ``None`` nor a list of non-empty strings.

        Notes:
            ``None`` means "not sent" and an **empty list** means "require
            nothing from now on", exactly as for the certification list beside
            it — and this is the field somebody clears after discovering that a
            skill requirement was stopping a service being planned at all.
        """
        if value is None:
            return None
        if not isinstance(value, list):
            raise MTInterventionTypeUpdateRequestInvalidSkills(
                f"Invalid required_skill_codes: {value!r}. "
                f"Must be a list of skill codes."
            )
        codes: List[str] = []
        for entry in value:
            if not isinstance(entry, str) or not entry.strip():
                raise MTInterventionTypeUpdateRequestInvalidSkills(
                    f"Invalid skill code: {entry!r}. Must be a non-empty string."
                )
            normalized = entry.strip().upper()
            if normalized not in codes:
                codes.append(normalized)
        return codes

    @field_validator("base_hourly_rate_ht", mode="before")
    def validate_base_hourly_rate_ht(
        cls, value: Union[str, int, float, Decimal, None]
    ) -> Optional[Decimal]:
        """Validates that the rate is absent, cleared, or strictly positive.

        Args:
            value (Union[str, int, float, Decimal, None]): Raw rate.

        Returns:
            Optional[Decimal]: The rate, or ``None`` to bill at the agency rate.

        Raises:
            MTInterventionTypeUpdateRequestInvalidRate: If ``value`` cannot be
                read as a number, or is not strictly positive.

        Notes:
            Zero is refused rather than stored. A rate of nothing would price
            every line of this service at nothing, and it is indistinguishable
            on screen from the empty box that means "use the agency rate" —
            which is the mistake somebody clearing the field is most likely to
            make.

            Built through ``str`` so a JSON float never becomes a binary
            approximation. Money does not touch a float anywhere in the pricing
            path, and this is one of the boundaries where that holds.
        """
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise MTInterventionTypeUpdateRequestInvalidRate(
                f"Invalid base_hourly_rate_ht: {value!r}. Must be a number."
            )
        try:
            rate = Decimal(str(value))
        except (ArithmeticError, ValueError):
            raise MTInterventionTypeUpdateRequestInvalidRate(
                f"Invalid base_hourly_rate_ht: {value!r}. Must be a number."
            ) from None
        if not rate.is_finite() or rate <= 0:
            raise MTInterventionTypeUpdateRequestInvalidRate(
                f"Invalid base_hourly_rate_ht: {value!r}. Must be positive, or "
                "omitted to bill at the agency rate."
            )
        return rate
