from __future__ import annotations

# Standard library imports
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Optional, Tuple, Union

# Third-party imports
from pydantic import BaseModel, Field, field_validator

# First-party imports
from models.enums import BillingPeriodicity, Language
from models.settings.exceptions import (
    MTBillingSettingsInvalidDate,
    MTBillingSettingsInvalidId,
    MTBillingSettingsInvalidIndemnity,
    MTBillingSettingsInvalidPaymentTerms,
    MTBillingSettingsInvalidPenaltyMultiplier,
    MTBillingSettingsInvalidPeriodicity,
    MTBillingSettingsInvalidUpdatedBy,
)


class BillingSettings(BaseModel):
    """The invoicing rules an administrator or manager may change at runtime.

    Attributes:
        SINGLETON_ID (ClassVar[str]): The identifier of the one settings row.
        CENTS (ClassVar[Decimal]): The quantum money is rounded to.
        MIN_PAYMENT_TERMS_DAYS (ClassVar[int]): Shortest terms accepted.
        MAX_PAYMENT_TERMS_DAYS (ClassVar[int]): The statutory ceiling on agreed
            payment terms.
        MIN_PENALTY_MULTIPLIER (ClassVar[int]): The statutory floor on the
            late-payment rate.
        MAX_PENALTY_MULTIPLIER (ClassVar[int]): Highest multiplier accepted.
        MAX_INDEMNITY (ClassVar[Decimal]): Highest recovery indemnity accepted.
        TERMS (ClassVar[...]): The sentence describing the terms, per language.
        id (str): Identifier. Always :attr:`SINGLETON_ID`.
        periodicity (BillingPeriodicity): How often customers are invoiced.
        payment_terms_days (int): How long a customer has to pay.
        late_penalty_multiplier (int): How many times the legal interest rate a
            late payment is charged at.
        recovery_indemnity_eur (Decimal): The fixed recovery indemnity.
        escompte_offered (bool): Whether a discount for early settlement is
            offered.
        updated_by (Optional[str]): The account that last changed these.
        updated_at (Optional[datetime]): When they were last changed.

    Notes:
        - **Every field here is printed on the invoice.** That is the test for
          whether a setting belongs in this model rather than in ``app.yaml``:
          these are statements the agency makes to its customers, and changing
          one is a commercial decision a manager takes, not a deployment.
        - **One row, fixed identifier**, exactly as the planning rules are. These
          are agency-wide, and a table able to hold two of them invites the
          question of which one an invoice was issued under — a question a
          printed document cannot answer afterwards.
        - The configuration file still carries the defaults. They seed the row
          the first time it is read.
        - Changing any of these affects the **next** generation run. An invoice
          already issued keeps the terms it was printed with, because the terms
          are part of what the customer was told, not a live lookup.
        - ``escompte_offered`` exists because saying nothing is itself a
          non-conformity: a French invoice must state the discount for early
          settlement *or* state that there is none, so the flag decides which
          sentence is printed and never whether one is.
    """

    SINGLETON_ID: ClassVar[str] = "billing-settings"
    CENTS: ClassVar[Decimal] = Decimal("0.01")
    MIN_PAYMENT_TERMS_DAYS: ClassVar[int] = 1
    MAX_PAYMENT_TERMS_DAYS: ClassVar[int] = 60
    MIN_PENALTY_MULTIPLIER: ClassVar[int] = 1
    MAX_PENALTY_MULTIPLIER: ClassVar[int] = 10
    MAX_INDEMNITY: ClassVar[Decimal] = Decimal("1000.00")
    TERMS: ClassVar[Tuple[Tuple[Language, str], ...]] = (
        (
            Language.FR,
            "Paiement à {days} jours. Escompte pour paiement anticipé : {escompte}.",
        ),
        (
            Language.EN,
            "Payment within {days} days. Early-settlement discount: {escompte}.",
        ),
    )

    id: str = Field(
        default=SINGLETON_ID,
        description="Identifier. Always the singleton row.",
    )
    periodicity: BillingPeriodicity = Field(
        default=BillingPeriodicity.MONTHLY,
        description="How often customers are invoiced.",
    )
    payment_terms_days: int = Field(
        default=30,
        description="How long a customer has to pay.",
    )
    late_penalty_multiplier: int = Field(
        default=3,
        description="Times the legal interest rate a late payment is charged at.",
    )
    recovery_indemnity_eur: Decimal = Field(
        default=Decimal("40.00"),
        description="The fixed recovery indemnity.",
    )
    escompte_offered: bool = Field(
        default=False,
        description="Whether a discount for early settlement is offered.",
    )
    updated_by: Optional[str] = Field(
        default=None,
        description="The account that last changed these.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="When they were last changed.",
    )

    ############################
    # Fields Validation Methods #
    ############################

    @field_validator("id", mode="before")
    def validate_id(cls, value: Optional[str]) -> str:
        """Validates that ``id`` names the singleton row.

        Args:
            value (Optional[str]): Raw ``id`` value.

        Returns:
            str: The identifier.

        Raises:
            MTBillingSettingsInvalidId: If ``value`` is not the singleton
                identifier.

        Notes:
            Refusing any other value is what keeps the table to one row even if
            a caller invents an identifier: there is nowhere else for a second
            set of invoicing rules to live.
        """
        if value is None:
            return cls.SINGLETON_ID
        if not isinstance(value, str) or value.strip() != cls.SINGLETON_ID:
            raise MTBillingSettingsInvalidId(
                f"Invalid id: {value!r}. The billing settings are a single "
                f"row and must be identified as {cls.SINGLETON_ID!r}."
            )
        return cls.SINGLETON_ID

    @field_validator("periodicity", mode="before")
    def validate_periodicity(
        cls, value: Optional[Union[str, BillingPeriodicity]]
    ) -> BillingPeriodicity:
        """Validates that ``periodicity`` names a known billing rule.

        Args:
            value (Optional[Union[str, BillingPeriodicity]]): Raw periodicity.
                ``None`` falls back to monthly.

        Returns:
            BillingPeriodicity: The coerced periodicity.

        Raises:
            MTBillingSettingsInvalidPeriodicity: If ``value`` is not a known
                periodicity.

        Notes:
            Monthly is the fallback because it is what a home-care agency
            invoices on by default, and because it is the periodicity whose
            windows a customer recognises without being told.
        """
        if value is None:
            return BillingPeriodicity.MONTHLY
        if isinstance(value, BillingPeriodicity):
            return value
        try:
            return BillingPeriodicity(value)
        except ValueError:
            raise MTBillingSettingsInvalidPeriodicity(
                f"Invalid periodicity: {value!r}. Must be one of: "
                f"{', '.join(BillingPeriodicity.values())}."
            ) from None

    @field_validator("payment_terms_days", mode="before")
    def validate_payment_terms_days(cls, value: Optional[Union[int, str]]) -> int:  # noqa: E501
        """Validates that the payment terms are within the legal range.

        Args:
            value (Optional[Union[int, str]]): Raw number of days.

        Returns:
            int: The validated number of days.

        Raises:
            MTBillingSettingsInvalidPaymentTerms: If ``value`` is not a whole
                number of days within the accepted range.

        Notes:
            The ceiling is statutory rather than a preference — the code de
            commerce caps agreed terms — so a longer one would print an
            obligation the agency could not enforce if it ever had to.
        """
        if value is None:
            raise MTBillingSettingsInvalidPaymentTerms(
                "Invalid payment_terms_days: a number of days is required."
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillingSettingsInvalidPaymentTerms(
                f"Invalid payment_terms_days: {value!r}. Must be a whole "
                f"number of days."
            )
        if not cls.MIN_PAYMENT_TERMS_DAYS <= value <= cls.MAX_PAYMENT_TERMS_DAYS:  # noqa: E501
            raise MTBillingSettingsInvalidPaymentTerms(
                f"Invalid payment_terms_days: {value!r}. Must be within "
                f"{cls.MIN_PAYMENT_TERMS_DAYS}..{cls.MAX_PAYMENT_TERMS_DAYS}."
            )
        return value

    @field_validator("late_penalty_multiplier", mode="before")
    def validate_late_penalty_multiplier(cls, value: Optional[Union[int, str]]) -> int:  # noqa: E501
        """Validates that the late-payment multiplier is at least the floor.

        Args:
            value (Optional[Union[int, str]]): Raw multiplier.

        Returns:
            int: The validated multiplier.

        Raises:
            MTBillingSettingsInvalidPenaltyMultiplier: If ``value`` is not a
                whole multiplier within the accepted range.

        Notes:
            The floor is one because a penalty below the legal interest rate is
            not a penalty. Three is the default and the figure the printed
            sentence has always named.
        """
        if value is None:
            raise MTBillingSettingsInvalidPenaltyMultiplier(
                "Invalid late_penalty_multiplier: a multiplier is required."
            )
        if isinstance(value, bool) or not isinstance(value, int):
            raise MTBillingSettingsInvalidPenaltyMultiplier(
                f"Invalid late_penalty_multiplier: {value!r}. "  # noqa: E501
                "Must be a whole number."
            )
        if not cls.MIN_PENALTY_MULTIPLIER <= value <= cls.MAX_PENALTY_MULTIPLIER:  # noqa: E501
            raise MTBillingSettingsInvalidPenaltyMultiplier(
                f"Invalid late_penalty_multiplier: {value!r}. Must be within "
                f"{cls.MIN_PENALTY_MULTIPLIER}..{cls.MAX_PENALTY_MULTIPLIER}."
            )
        return value

    @field_validator("recovery_indemnity_eur", mode="before")
    def validate_recovery_indemnity_eur(
        cls, value: Optional[int, float, str, Decimal]
    ) -> Decimal:
        """Validates that the recovery indemnity is a positive amount.

        Args:
            value (Optional[int, float, str, Decimal]): Raw amount.

        Returns:
            Decimal: The amount, rounded to the cent.

        Raises:
            MTBillingSettingsInvalidIndemnity: If ``value`` is missing,
                unreadable, or outside the accepted range.

        Notes:
            Configurable rather than fixed at forty euros because the statutory
            figure has been raised before and will be again, and an agency
            should not need a release to print the current one. Routed through
            ``str`` so a JSON float keeps its exact value.
        """
        if value is None:
            raise MTBillingSettingsInvalidIndemnity(
                "Invalid recovery_indemnity_eur: an amount is required."
            )
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTBillingSettingsInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {value!r}. Must be a "
                f"non-negative decimal."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTBillingSettingsInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {value!r}. Must be a "
                f"non-negative decimal."
            ) from None
        if not coerced.is_finite() or not Decimal(0) <= coerced <= cls.MAX_INDEMNITY:  # noqa: E501
            raise MTBillingSettingsInvalidIndemnity(
                f"Invalid recovery_indemnity_eur: {coerced!r}. Must be within "
                f"0..{cls.MAX_INDEMNITY}."
            )
        return coerced.quantize(cls.CENTS)

    @field_validator("updated_by", mode="before")
    def validate_updated_by(cls, value: Optional[str]) -> Optional[str]:
        """Validates that the editing account, when given, is identified.

        Args:
            value (Optional[str]): Raw ``updated_by`` value.

        Returns:
            Optional[str]: The account identifier, or ``None``.

        Raises:
            MTBillingSettingsInvalidUpdatedBy: If ``value`` is neither ``None``
                nor a non-empty string.

        Notes:
            Optional because the seeded defaults were nobody's decision. Once
            somebody edits them it is not: "who put the payment terms to sixty
            days?" is a question with a name attached.
        """
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise MTBillingSettingsInvalidUpdatedBy(
                f"Invalid updated_by: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("updated_at", mode="before")
    def validate_updated_at(
        cls, value: Optional[Union[datetime, str]]
    ) -> Optional[datetime]:
        """Validates that ``updated_at`` is a datetime.

        Args:
            value (Optional[Union[datetime, str]]): Raw timestamp value.

        Returns:
            Optional[datetime]: The timestamp, or ``None``.

        Raises:
            MTBillingSettingsInvalidDate: If ``value`` is neither ``None`` nor a
                datetime or ISO-8601 string.
        """
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                raise MTBillingSettingsInvalidDate(
                    f"Invalid updated_at: {value!r}. "  # noqa: E501
                    "Must be an ISO-8601 datetime."
                ) from None
        raise MTBillingSettingsInvalidDate(
            f"Invalid updated_at: {value!r}. Must be a datetime."
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def due_date(self, issued_on: date) -> date:
        """Return the day payment falls due for an invoice issued on a date.

        Args:
            issued_on (date): The invoice date.

        Returns:
            date: The due date.

        Notes:
            Counted from the invoice date rather than from the end of the period
            it bills, which is what the printed terms say and what the customer
            reads. Computing it here rather than at each call site is what keeps
            the due date on the document and the due date in the record the
            same day.
        """
        return issued_on + timedelta(days=self.payment_terms_days)

    def window(self, day: date) -> Tuple[date, date]:
        """Return the billing window containing a day, under these rules.

        Args:
            day (date): Any day inside the wanted period.

        Returns:
            Tuple[date, date]: The period's first and last day, both inclusive.

        Notes:
            Delegated to the periodicity rather than reimplemented, so a caller
            holding the settings never has to reach through to the enumeration
            and cannot accidentally resolve a window under a different rule from
            the one the agency configured.
        """
        return self.periodicity.window(day)

    def previous_window(self, day: date) -> Tuple[date, date]:
        """Return the window before the one containing a day.

        Args:
            day (date): Any day inside the current period.

        Returns:
            Tuple[date, date]: The previous period's first and last day.

        Notes:
            This is what a generation run actually asks for: a period is
            invoiced once it has been delivered, so "bill the last one" is the
            ordinary case and today's own period is the exception.
        """
        return self.periodicity.previous_window(day)

    def describe_terms(self, language: Language = Language.FR) -> str:
        """Return the payment-terms sentence printed on an invoice.

        Args:
            language (Language): The language to write it in. Defaults to
                French.

        Returns:
            str: The sentence naming the terms and the early-settlement
            discount.

        Notes:
            The discount is always stated, as "none" when none is offered:
            saying nothing about it is itself a non-conformity, so the flag
            decides which sentence is printed and never whether one is.
        """
        wording = dict(self.TERMS)[language]
        if language is Language.FR:
            escompte = "accordé" if self.escompte_offered else "néant"
        else:
            escompte = "offered" if self.escompte_offered else "none"
        return wording.format(days=self.payment_terms_days, escompte=escompte)
