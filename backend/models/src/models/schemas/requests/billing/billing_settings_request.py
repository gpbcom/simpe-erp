from __future__ import annotations

# Standard library imports
from decimal import Decimal, InvalidOperation
from typing import Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import BillingPeriodicity
from models.schemas.exceptions import (
    MTBillingSettingsRequestInvalidIndemnity,
    MTBillingSettingsRequestInvalidPaymentTerms,
    MTBillingSettingsRequestInvalidPenaltyMultiplier,
    MTBillingSettingsRequestInvalidPeriodicity,
)
from models.settings.billing_settings import BillingSettings


class BillingSettingsRequest(BaseModel):
    """The payload changing the invoicing rules.

    Attributes:
        periodicity (BillingPeriodicity): How often customers are invoiced.
        payment_terms_days (int): How long a customer has to pay.
        late_penalty_multiplier (int): How many times the legal interest rate a
            late payment is charged at.
        recovery_indemnity_eur (Decimal): The fixed recovery indemnity.
        escompte_offered (bool): Whether a discount for early settlement is
            offered.

    Notes:
        - The bounds repeat those on
          :class:`~models.settings.billing_settings.BillingSettings` rather than
          deferring to them, so a bad payload is refused as a 422 naming the
          field instead of surfacing from deeper in the stack as something
          vaguer. The stored model still enforces them — this is the outer of two
          gates, not a replacement for the inner one.
        - **Every field carries a default matching the stored model's**, and the
          whole rule set is sent on every save. A manager changing only the
          periodicity should not have to restate the payment terms, and a
          partial payload without defaults would silently reset the fields it
          omitted — on a document that goes to customers.
    """

    periodicity: BillingPeriodicity = Field(
        default=BillingPeriodicity.MONTHLY,
        description="How often customers are invoiced.",
    )
    payment_terms_days: int = Field(
        default=30,
        description="How long a customer has to pay, in days.",
    )
    late_penalty_multiplier: int = Field(
        default=3,
        description="Times the legal interest rate a late payment is charged at.",
    )
    recovery_indemnity_eur: Decimal = Field(
        default=Decimal("40.00"),
        description="The fixed recovery indemnity, in euros.",
    )
    escompte_offered: bool = Field(
        default=False,
        description="Whether a discount for early settlement is offered.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("periodicity", mode="before")
    def validate_periodicity(
        cls, value: Union[str, BillingPeriodicity, None]
    ) -> BillingPeriodicity:
        """Validates that ``periodicity`` names a known billing rule.

        Args:
            value (Union[str, BillingPeriodicity, None]): Raw periodicity.

        Returns:
            BillingPeriodicity: The coerced periodicity.

        Raises:
            MTBillingSettingsRequestInvalidPeriodicity: If ``value`` is not a
                known periodicity.
        """
        if value is None:
            return BillingPeriodicity.MONTHLY
        if isinstance(value, BillingPeriodicity):
            return value
        try:
            return BillingPeriodicity(value)
        except ValueError:
            raise MTBillingSettingsRequestInvalidPeriodicity(
                f"Invalid periodicity: {value!r}. Must be one of: "
                f"{', '.join(BillingPeriodicity.values())}."
            ) from None

    @field_validator("payment_terms_days", mode="before")
    def validate_payment_terms_days(cls, value: Union[int, str, None]) -> int:
        """Validates that the payment terms are within the legal range.

        Args:
            value (Union[int, str, None]): Raw number of days.

        Returns:
            int: The validated number of days.

        Raises:
            MTBillingSettingsRequestInvalidPaymentTerms: If ``value`` is not a
                whole number of days within the accepted range.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillingSettingsRequestInvalidPaymentTerms(
                f"Invalid payment_terms_days: {value!r}. Must be a whole "
                f"number of days."
            )
        if not (
            BillingSettings.MIN_PAYMENT_TERMS_DAYS
            <= value
            <= BillingSettings.MAX_PAYMENT_TERMS_DAYS
        ):
            raise MTBillingSettingsRequestInvalidPaymentTerms(
                f"Invalid payment_terms_days: {value!r}. Must be within "
                f"{BillingSettings.MIN_PAYMENT_TERMS_DAYS}.."
                f"{BillingSettings.MAX_PAYMENT_TERMS_DAYS}."
            )
        return value

    @field_validator("late_penalty_multiplier", mode="before")
    def validate_late_penalty_multiplier(cls, value: Union[int, str, None]) -> int:
        """Validates that the late-payment multiplier is within range.

        Args:
            value (Union[int, str, None]): Raw multiplier.

        Returns:
            int: The validated multiplier.

        Raises:
            MTBillingSettingsRequestInvalidPenaltyMultiplier: If ``value`` is
                not a whole multiplier within the accepted range.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillingSettingsRequestInvalidPenaltyMultiplier(
                f"Invalid late_penalty_multiplier: {value!r}. Must be a whole number."
            )
        if not (
            BillingSettings.MIN_PENALTY_MULTIPLIER
            <= value
            <= BillingSettings.MAX_PENALTY_MULTIPLIER
        ):
            raise MTBillingSettingsRequestInvalidPenaltyMultiplier(
                f"Invalid late_penalty_multiplier: {value!r}. Must be within "
                f"{BillingSettings.MIN_PENALTY_MULTIPLIER}.."
                f"{BillingSettings.MAX_PENALTY_MULTIPLIER}."
            )
        return value

    @field_validator("recovery_indemnity_eur", mode="before")
    def validate_recovery_indemnity_eur(
        cls, value: Union[int, float, str, Decimal, None]
    ) -> Decimal:
        """Validates that the recovery indemnity is a positive amount.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw amount.

        Returns:
            Decimal: The amount as a :class:`~decimal.Decimal`.

        Raises:
            MTBillingSettingsRequestInvalidIndemnity: If ``value`` is missing,
                unreadable, or outside the accepted range.

        Notes:
            Routed through ``str`` before reaching :class:`~decimal.Decimal`, so
            a JSON float keeps its exact value. Money never touches a float in
            this application, and an indemnity is money.
        """
        if value is None:
            raise MTBillingSettingsRequestInvalidIndemnity(
                "Invalid recovery_indemnity_eur: an amount is required."
            )
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise MTBillingSettingsRequestInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {value!r}. Must be a "
                f"non-negative decimal."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTBillingSettingsRequestInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {value!r}. Must be a "
                f"non-negative decimal."
            ) from None
        if (
            not coerced.is_finite()
            or not Decimal(0) <= coerced <= BillingSettings.MAX_INDEMNITY
        ):
            raise MTBillingSettingsRequestInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {coerced!r}. Must be within "
                f"0..{BillingSettings.MAX_INDEMNITY}."
            )
        return coerced

    ############################
    # Publicly Exposed Methods #
    ############################

    def apply_to(self, settings: BillingSettings, actor: str) -> BillingSettings:
        """Return the stored settings with this payload written onto them.

        Args:
            settings (BillingSettings): The rules as they stand.
            actor (str): The account making the change.

        Returns:
            BillingSettings: A new settings record carrying the payload.

        Notes:
            Built through ``model_validate`` rather than ``model_copy``, because
            ``model_copy`` does not re-run validators: an update taking that
            route would store a payment term the stored model would have refused,
            and the refusal would only surface the next time somebody read it.
        """
        merged = settings.model_dump()
        merged.update(self.model_dump())
        merged["updated_by"] = actor
        return BillingSettings.model_validate(merged)
