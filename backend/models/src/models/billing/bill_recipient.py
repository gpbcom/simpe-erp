from __future__ import annotations

# Standard library imports
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Dict, Optional, Union

# Third-party imports
from pydantic import (  # noqa: E501
    BaseModel,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

# First-party imports
from models.billing.exceptions import (
    MTBillRecipientInvalidAddress,
    MTBillRecipientInvalidKind,
    MTBillRecipientInvalidName,
    MTBillRecipientInvalidServiceCode,
    MTBillRecipientInvalidShare,
    MTBillRecipientInvalidSiren,
    MTBillRecipientInvalidVatNumber,
    MTBillRecipientMissingSiren,
    MTBillRecipientUnexpectedSiren,
)
from models.enums import RecipientKind
from models.geo.postal_address import PostalAddress


class BillRecipient(BaseModel):
    """The party that owes an invoice, which is not always the person cared for.

    Attributes:
        SIREN_LENGTH (ClassVar[int]): Digits in a French SIREN.
        MAX_NAME_LENGTH (ClassVar[int]): Longest accepted name.
        MAX_VAT_LENGTH (ClassVar[int]): Longest accepted VAT number.
        MAX_SERVICE_CODE_LENGTH (ClassVar[int]): Longest accepted service code.
        CENTS (ClassVar[Decimal]): The quantum money is rounded to.
        kind (RecipientKind): Whether a household, a business or a public body.
        name (str): Who the invoice is made out to.
        address (PostalAddress): Where it is addressed.
        siren (Optional[str]): The legal identifier, for a professional.
        vat_number (Optional[str]): The intra-community VAT number, if any.
        service_code (Optional[str]): The routing code inside a public body.
        share_ttc (Optional[Decimal]): What this party owes of the total, when
            the invoice is split between payers.

    Notes:
        - **A recipient is not a customer.** Care is delivered to a household,
          and the bill for it may be addressed to a conseil départemental, a
          mutuelle or an employer. Keeping them apart is what lets an invoice
          name both — the household stays on the bill as the party the work was
          delivered *to*, which is what the structured format calls the
          ship-to party, while this is the party it is *billed* to.
        - **Denormalised onto the invoice, like the customer's own name.** An
          invoice is a legal document that must reprint identically for ten
          years; a payer who is renamed or moves must not retroactively change
          who last quarter's invoice was addressed to. That is the same trade
          :class:`~models.planning.intervention.Intervention` makes with the
          assistant's name.
        - **The identifier rules are asymmetric on purpose.** A professional
          without a SIREN cannot be routed to at all, and a household with one
          would be read as a company by every downstream system. So one is
          required and the other refused, rather than both being merely
          optional — see :meth:`check_identifiers`.
        - ``share_ttc`` exists for the case a single course of care is funded by
          two parties, which is the ordinary shape of an APA arrangement. It is
          deliberately **not** a percentage: a percentage of a rounded total is
          a second rounding, and the two payers' shares would stop summing to
          the invoice. Whether such a split is one invoice with two recipients
          or two linked invoices is a question this model does not answer — it
          records what *this* recipient owes and no more.
    """

    SIREN_LENGTH: ClassVar[int] = 9
    MAX_NAME_LENGTH: ClassVar[int] = 255
    MAX_VAT_LENGTH: ClassVar[int] = 20
    MAX_SERVICE_CODE_LENGTH: ClassVar[int] = 64
    CENTS: ClassVar[Decimal] = Decimal("0.01")

    kind: RecipientKind = Field(
        default=RecipientKind.INDIVIDUAL,
        description="Whether a household, a business or a public body.",
    )
    name: str = Field(description="Who the invoice is made out to.")
    address: PostalAddress = Field(description="Where it is addressed.")
    siren: Optional[str] = Field(
        default=None,
        description="The legal identifier, required for a professional.",
    )
    vat_number: Optional[str] = Field(
        default=None,
        description="The intra-community VAT number, if any.",
    )
    service_code: Optional[str] = Field(
        default=None,
        description="The routing code inside a public body.",
    )
    share_ttc: Optional[Decimal] = Field(
        default=None,
        description="What this party owes of the total, when it is split.",
    )

    #############################
    # Fields Validation Methods #
    #############################

    @field_validator("kind", mode="before")
    def validate_kind(cls, value: Union[str, RecipientKind, None]) -> RecipientKind:
        """Validates that ``kind`` names a known kind of recipient.

        Args:
            value (Union[str, RecipientKind, None]): Raw kind. ``None`` falls
                back to a private individual.

        Returns:
            RecipientKind: The coerced kind.

        Raises:
            MTBillRecipientInvalidKind: If ``value`` is not a known kind.

        Notes:
            The fallback is the *individual*, which is both the ordinary case
            for this agency and the safe one: it triggers reporting rather than
            transmission, so a missing value cannot cause a document to be sent
            to a platform for a party nobody identified.
        """
        if value is None:
            return RecipientKind.INDIVIDUAL
        if isinstance(value, RecipientKind):
            return value
        try:
            return RecipientKind(value)
        except ValueError:
            raise MTBillRecipientInvalidKind(
                f"Invalid kind: {value!r}. Must be one of: "
                f"{', '.join(RecipientKind.values())}."
            ) from None

    @field_validator("name", mode="before")
    def validate_name(cls, value: Optional[str]) -> str:
        """Validates that the recipient is named.

        Args:
            value (Optional[str]): Raw name.

        Returns:
            str: The stripped name.

        Raises:
            MTBillRecipientInvalidName: If ``value`` is not a non-empty string
                within :attr:`MAX_NAME_LENGTH`.

        Notes:
            An invoice with no addressee is not an invoice. Falling back to the
            identifier would print a SIREN on a document somebody has to
            recognise as addressed to them.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTBillRecipientInvalidName(
                f"Invalid name: {value!r}. Must be a non-empty string."
            )
        cleaned = value.strip()
        if len(cleaned) > cls.MAX_NAME_LENGTH:
            raise MTBillRecipientInvalidName(
                f"Invalid name: {len(cleaned)} characters. Must be at most "
                f"{cls.MAX_NAME_LENGTH}."
            )
        return cleaned

    @field_validator("address", mode="before")
    def validate_address(
        cls, value: Union[PostalAddress, Dict[str, JsonValue], None]
    ) -> Union[PostalAddress, Dict[str, JsonValue]]:
        """Validates that ``address`` is an address or a mapping.

        Args:
            value (Union[PostalAddress, Dict[str, JsonValue], None]): Raw
                address value.

        Returns:
            Union[PostalAddress, Dict[str, JsonValue]]: The value handed back
            for Pydantic to build.

        Raises:
            MTBillRecipientInvalidAddress: If ``value`` is neither a
                :class:`~models.geo.postal_address.PostalAddress` nor a mapping.
        """
        if value is None or not isinstance(value, (PostalAddress, dict)):
            raise MTBillRecipientInvalidAddress(
                f"Invalid address: {value!r}. Must be a PostalAddress or a mapping."
            )
        return value

    @field_validator("siren", mode="before")
    def validate_siren(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``siren``, when given, is a well-formed SIREN.

        Args:
            value (Optional[str]): Raw identifier, with or without spacing.

        Returns:
            Optional[str]: The nine digits, or ``None``.

        Raises:
            MTBillRecipientInvalidSiren: If ``value`` is neither ``None`` nor
                nine digits passing the Luhn check.

        Notes:
            - Separators are stripped before checking, because these get typed
              by hand off a letterhead and the spacing varies by who is reading.
            - **The Luhn check is the point.** Nine digits is a shape; the
              checksum is what catches the transposed pair, and catching it here
              means the failure is a 422 naming the field rather than a platform
              rejecting the invoice after a number has been drawn from a series
              that cannot have gaps.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTBillRecipientInvalidSiren(
                f"Invalid siren: {value!r}. Must be a string of nine digits."
            )
        cleaned = value.replace(" ", "").replace("-", "")
        if not cleaned:
            return None
        if not cleaned.isdigit() or len(cleaned) != cls.SIREN_LENGTH:
            raise MTBillRecipientInvalidSiren(
                f"Invalid siren: {value!r}. Must be exactly {cls.SIREN_LENGTH} digits."
            )
        total = 0
        for position, digit in enumerate(reversed(cleaned)):
            doubled = int(digit) * (2 if position % 2 else 1)
            total += doubled - 9 if doubled > 9 else doubled
        if total % 10 != 0:
            raise MTBillRecipientInvalidSiren(
                f"Invalid siren: {cleaned!r}. The check digit does not match, "
                f"so two figures have most likely been transposed."
            )
        return cleaned

    @field_validator("vat_number", mode="before")
    def validate_vat_number(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``vat_number``, when given, is usable.

        Args:
            value (Optional[str]): Raw VAT number.

        Returns:
            Optional[str]: The upper-cased number without separators, or
            ``None``.

        Raises:
            MTBillRecipientInvalidVatNumber: If ``value`` is neither ``None``
                nor an alphanumeric string within :attr:`MAX_VAT_LENGTH`.

        Notes:
            Checked for shape rather than for country-specific structure. The
            member states do not agree on a format, and refusing a valid Belgian
            number because a French one looks different would be a validator
            inventing a rule the tax authorities do not have.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTBillRecipientInvalidVatNumber(
                f"Invalid vat_number: {value!r}. Must be a string."
            )
        cleaned = value.replace(" ", "").replace("-", "").upper()
        if not cleaned:
            return None
        if not cleaned.isalnum() or len(cleaned) > cls.MAX_VAT_LENGTH:
            raise MTBillRecipientInvalidVatNumber(
                f"Invalid vat_number: {value!r}. Must be alphanumeric and at "
                f"most {cls.MAX_VAT_LENGTH} characters."
            )
        return cleaned

    @field_validator("service_code", mode="before")
    def validate_service_code(cls, value: Optional[str]) -> Optional[str]:
        """Validates that ``service_code``, when given, is usable.

        Args:
            value (Optional[str]): Raw service code.

        Returns:
            Optional[str]: The stripped code, or ``None``.

        Raises:
            MTBillRecipientInvalidServiceCode: If ``value`` is neither ``None``
                nor a string within :attr:`MAX_SERVICE_CODE_LENGTH`.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise MTBillRecipientInvalidServiceCode(
                f"Invalid service_code: {value!r}. Must be a string."
            )
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) > cls.MAX_SERVICE_CODE_LENGTH:
            raise MTBillRecipientInvalidServiceCode(
                f"Invalid service_code: {len(cleaned)} characters. Must be at "
                f"most {cls.MAX_SERVICE_CODE_LENGTH}."
            )
        return cleaned

    @field_validator("share_ttc", mode="before")
    def validate_share_ttc(
        cls, value: Union[int, float, str, Decimal, None]
    ) -> Optional[Decimal]:
        """Validates that the funded share, when given, is a positive amount.

        Args:
            value (Union[int, float, str, Decimal, None]): Raw amount.

        Returns:
            Optional[Decimal]: The amount rounded to the cent, or ``None``.

        Raises:
            MTBillRecipientInvalidShare: If ``value`` is unreadable or negative.

        Notes:
            ``None`` means "the whole invoice", which is what a single payer
            owes and therefore the ordinary case. Zero is refused: a party that
            owes nothing is not a recipient of the invoice, they are an entry
            somebody forgot to remove. Routed through ``str`` so a JSON float
            keeps its exact value.
        """
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):  # noqa: E501
            raise MTBillRecipientInvalidShare(
                f"Invalid share_ttc: {value!r}. Must be a positive decimal."
            )
        try:
            coerced = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise MTBillRecipientInvalidShare(
                f"Invalid share_ttc: {value!r}. Must be a positive decimal."
            ) from None
        if not coerced.is_finite() or coerced <= 0:
            raise MTBillRecipientInvalidShare(
                f"Invalid share_ttc: {coerced!r}. Must be strictly positive; "
                f"leave it unset when this party owes the whole invoice."
            )
        return coerced.quantize(cls.CENTS)

    @model_validator(mode="after")
    def check_identifiers(self) -> BillRecipient:
        """Ensure the identifiers match the kind of party.

        Returns:
            BillRecipient: ``self`` for chaining.

        Raises:
            MTBillRecipientMissingSiren: If a professional carries no SIREN.
            MTBillRecipientUnexpectedSiren: If a household carries one.

        Notes:
            **Both directions are errors, and neither is pedantry.** A business
            or a public body is *routed* on its SIREN, so an invoice without one
            cannot be delivered — it would be accepted here and rejected by the
            platform, after the number was spent. A household with one would be
            read as a company by every downstream system, and the invoice would
            be transmitted for delivery to a party that does not exist.
        """
        if self.kind.requires_legal_identifier() and not self.siren:
            raise MTBillRecipientMissingSiren(
                f"Invalid siren: a recipient of kind {self.kind.value!r} is "
                f"routed on its SIREN and cannot be invoiced without one."
            )
        if not self.kind.requires_legal_identifier() and self.siren:
            raise MTBillRecipientUnexpectedSiren(
                f"Invalid siren: {self.siren!r} was given for a private "
                f"individual, who has none. Set the kind instead."
            )
        return self

    @model_validator(mode="after")
    def check_service_code(self) -> BillRecipient:
        """Ensure only a public body carries a routing service code.

        Returns:
            BillRecipient: ``self`` for chaining.

        Raises:
            MTBillRecipientInvalidServiceCode: If a service code is set on a
                recipient that is not a public body.

        Notes:
            Refused rather than ignored, because a code carried by a business
            would be silently dropped on the way out and whoever entered it
            would go on believing the invoice was routed by it.
        """
        if self.service_code and self.kind is not RecipientKind.PUBLIC:
            raise MTBillRecipientInvalidServiceCode(
                f"Invalid service_code: {self.service_code!r} only applies to "
                f"a public body, not to a recipient of kind "
                f"{self.kind.value!r}."
            )
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_individual(self) -> bool:
        """Return whether the invoice is addressed to a private person.

        Returns:
            bool: ``True`` for a household.

        Notes:
            The question that decides the regime: an individual is *reported*,
            a professional is *transmitted*.
        """
        return self.kind is RecipientKind.INDIVIDUAL

    def legal_identifier(self) -> Optional[str]:
        """Return the identifier a structured invoice is routed on.

        Returns:
            Optional[str]: The SIREN, or ``None`` for a household.

        Notes:
            Named for what it is *for* rather than for what it holds, because
            the structured format asks for "the buyer's legal registration
            identifier" and the answer here happens to be a SIREN. A reader
            following the mapping should not have to know that.
        """
        return self.siren

    def owes(self, total_ttc: Decimal) -> Decimal:
        """Return what this party owes of an invoice total.

        Args:
            total_ttc (Decimal): The invoice total including tax.

        Returns:
            Decimal: The funded share when one is set, otherwise the whole
            total.

        Notes:
            The whole total is the answer for a single payer, which is almost
            every invoice. Computing it here rather than at the call sites is
            what stops "the amount due" and "the invoice total" drifting apart
            on the one document where they legitimately differ.
        """
        return self.share_ttc if self.share_ttc is not None else total_ttc
