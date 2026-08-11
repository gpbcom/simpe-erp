from __future__ import annotations

# Standard library imports
from decimal import Decimal
from typing import Optional, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.configuration.exceptions import (
    MTBillingConfigInvalidIndemnity,
    MTBillingConfigInvalidPaymentTerms,
    MTBillingConfigInvalidPenaltyMultiplier,
    MTBillingConfigInvalidPeriodicity,
)
from models.enums import BillingPeriodicity
from models.settings.billing_settings import BillingSettings


class BillingConfig(BaseModel):
    """The invoicing rules a deployment starts with.

    Attributes:
        periodicity (BillingPeriodicity): How often customers are invoiced.
        payment_terms_days (int): How long a customer has to pay.
        late_penalty_multiplier (int): How many times the legal interest rate a
            late payment is charged at.
        recovery_indemnity_eur (Decimal): The fixed recovery indemnity.
        escompte_offered (bool): Whether a discount for early settlement is
            offered.

    Notes:
        - **These are seeds, not the live rules.** The rules themselves live in
          the database, because the specification puts them in a manager's
          hands and a YAML value would need a deployment to change. This block
          is what the singleton row is created from the first time it is read,
          and is ignored ever afterwards — exactly the relationship
          :class:`~models.configuration.planning_config.PlanningConfig` has with
          the planning rules.
        - The defaults match the stored model's, so a deployment that configures
          nothing still issues a conforming French invoice: thirty-day terms,
          the legal interest rate trebled, a forty-euro recovery indemnity and
          no early-settlement discount.
        - The bounds are checked here as well as on the stored model. A bad
          value in a configuration file must fail at start-up with the field
          named, rather than at the first billing run of the month.
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

    #############################
    # Fields Validation Methods #
    #############################

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
            MTBillingConfigInvalidPeriodicity: If ``value`` is not a known
                periodicity.
        """
        if value is None:
            return BillingPeriodicity.MONTHLY
        if isinstance(value, BillingPeriodicity):
            return value
        try:
            return BillingPeriodicity(value)
        except ValueError:
            raise MTBillingConfigInvalidPeriodicity(
                f"Invalid periodicity: {value!r}. Must be one of: "
                f"{', '.join(BillingPeriodicity.values())}."
            ) from None

    @field_validator("payment_terms_days", mode="before")
    def validate_payment_terms_days(cls, value: Optional[Union[int, str]]) -> int:  # noqa: E501
        """Validates that the seeded payment terms are within the legal range.

        Args:
            value (Optional[Union[int, str]]): Raw number of days.

        Returns:
            int: The validated number of days.

        Raises:
            MTBillingConfigInvalidPaymentTerms: If ``value`` is not a whole
                number of days within the accepted range.
        """
        if value is None:
            return 30
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillingConfigInvalidPaymentTerms(
                f"Invalid payment_terms_days: {value!r}. Must be a whole "
                f"number of days."
            )
        if not (
            BillingSettings.MIN_PAYMENT_TERMS_DAYS
            <= value
            <= BillingSettings.MAX_PAYMENT_TERMS_DAYS
        ):
            raise MTBillingConfigInvalidPaymentTerms(
                f"Invalid payment_terms_days: {value!r}. Must be within "
                f"{BillingSettings.MIN_PAYMENT_TERMS_DAYS}.."
                f"{BillingSettings.MAX_PAYMENT_TERMS_DAYS}."
            )
        return value

    @field_validator("late_penalty_multiplier", mode="before")
    def validate_late_penalty_multiplier(cls, value: Optional[Union[int, str]]) -> int:   # noqa: E501
        """Validates that the seeded penalty multiplier is within range.

        Args:
            value (Optional[Union[int, str]]): Raw multiplier.

        Returns:
            int: The validated multiplier.

        Raises:
            MTBillingConfigInvalidPenaltyMultiplier: If ``value`` is not a whole
                multiplier within the accepted range.
        """
        if value is None:
            return 3
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillingConfigInvalidPenaltyMultiplier(
                f"Invalid late_penalty_multiplier: {value!r}. "   # noqa: E501
                "Must be a whole number."
            )
        if not (
            BillingSettings.MIN_PENALTY_MULTIPLIER
            <= value
            <= BillingSettings.MAX_PENALTY_MULTIPLIER
        ):
            raise MTBillingConfigInvalidPenaltyMultiplier(
                f"Invalid late_penalty_multiplier: {value!r}. Must be within "
                f"{BillingSettings.MIN_PENALTY_MULTIPLIER}.."
                f"{BillingSettings.MAX_PENALTY_MULTIPLIER}."
            )
        return value

    @field_validator("recovery_indemnity_eur", mode="before")
    def validate_recovery_indemnity_eur(
        cls, value: Union[int, float, str, Decimal, None]
    ) -> Decimal:
        """Validates that the seeded recovery indemnity is a positive amount.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw amount.

        Returns:
            Decimal: The amount as a :class:`~decimal.Decimal`.

        Raises:
            MTBillingConfigInvalidIndemnity: If ``value`` is unreadable or
                outside the accepted range.

        Notes:
            Routed through ``str`` so a YAML float keeps its exact value. An
            indemnity is money, and money never touches a float here.
        """
        if value is None:
            return Decimal("40.00")
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise MTBillingConfigInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {value!r}. Must be a "
                f"non-negative decimal."
            )
        try:
            coerced = Decimal(str(value))
        except ArithmeticError:
            raise MTBillingConfigInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {value!r}. Must be a "
                f"non-negative decimal."
            ) from None
        if (
            not coerced.is_finite()
            or not Decimal(0) <= coerced <= BillingSettings.MAX_INDEMNITY
        ):
            raise MTBillingConfigInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {coerced!r}. Must be within "
                f"0..{BillingSettings.MAX_INDEMNITY}."
            )
        return coerced

    #############################
    # Publicly Exposed Methods  #
    #############################

    def to_settings(self) -> BillingSettings:
        """Return the settings row this configuration seeds.

        Returns:
            BillingSettings: The rules a deployment starts with.

        Notes:
            Built here rather than by the repository so the mapping between the
            configuration block and the stored row lives in one place. The row
            is written with no ``updated_by``: the seeded defaults were nobody's
            decision, and attributing them to whoever happened to open the
            screen first would be a false audit trail.
        """
        return BillingSettings(
            periodicity=self.periodicity,
            payment_terms_days=self.payment_terms_days,
            late_penalty_multiplier=self.late_penalty_multiplier,
            recovery_indemnity_eur=self.recovery_indemnity_eur,
            escompte_offered=self.escompte_offered,
        )
