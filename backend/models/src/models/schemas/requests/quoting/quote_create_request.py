from __future__ import annotations

# Standard library imports
from typing import List, Optional

# Third-party imports
from pydantic import BaseModel, Field, JsonValue, field_validator

# First-party imports
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.schemas.exceptions import (
    MTQuoteCreateRequestInvalidCustomerId,
    MTQuoteCreateRequestInvalidLines,
    MTQuoteCreateRequestInvalidReference,
)


class QuoteCreateRequest(BaseModel):
    """The payload opening a new quote.

    Attributes:
        reference (str): The human-facing quote number.
        customer_id (str): The customer the offer is addressed to.
        lines (List[QuoteLine]): The services offered.

    Notes:
        - **The shape of this model is the permission.** The route used to take a
          whole :class:`~models.quoting.quote.Quote` as its body and trust three
          of its fields, which meant a caller could also send ``status``,
          ``validated_by`` and ``validated_at`` — accepting their own quote, in
          somebody else's name, without a manager ever seeing it. Those fields are
          absent here, so no payload can carry them.
        - ``company_id`` is absent for a stronger reason still. It decides whose
          accepted work a planning run schedules and whose calendar it rewrites,
          so a caller who could set it could write a quote into another agency and
          have that agency's assistants sent out to deliver it. It is taken from
          the credential in the route and cannot be sent at all.
        - ``authored_by`` is likewise absent, and was already overridden by the
          service for the same reason: a quote naming somebody else as its author
          would land in their list, and they would be the one a manager asks about
          a price they never set.
    """

    reference: str = Field(description="Human-facing quote number.")
    customer_id: str = Field(description="The customer the offer is addressed to.")
    lines: List[QuoteLine] = Field(
        default_factory=list,
        description="The services offered.",
    )

    @field_validator("reference", mode="before")
    def validate_reference(cls, value: Optional[str]) -> str:
        """Validates that ``reference`` is a non-empty string.

        Args:
            value (Optional[str]): Raw ``reference`` value.

        Returns:
            str: The stripped reference.

        Raises:
            MTQuoteCreateRequestInvalidReference: If ``value`` is not a
                non-empty string.

        Notes:
            Not generated when it is missing. The reference is what a customer
            quotes back on the phone, and one invented here would be a number
            the person who asked for the quote has never seen.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteCreateRequestInvalidReference(
                f"Invalid reference: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("customer_id", mode="before")
    def validate_customer_id(cls, value: Optional[str]) -> str:
        """Validates that ``customer_id`` names a customer.

        Args:
            value (Optional[str]): Raw ``customer_id`` value.

        Returns:
            str: The stripped identifier.

        Raises:
            MTQuoteCreateRequestInvalidCustomerId: If ``value`` is not a
                non-empty string.

        Notes:
            Whether the customer exists is not checked here — this payload
            cannot see the store — and the route answers 404 if they do not.
            What is checked is that one was named at all.
        """
        if not isinstance(value, str) or not value.strip():
            raise MTQuoteCreateRequestInvalidCustomerId(
                f"Invalid customer_id: {value!r}. Must be a non-empty string."
            )
        return value.strip()

    @field_validator("lines", mode="before")
    def validate_lines(cls, value: JsonValue) -> JsonValue:
        """Validates that ``lines`` is a list, when it is sent at all.

        Args:
            value (JsonValue): Raw ``lines`` value.

        Returns:
            JsonValue: The value handed back for the field type to parse.

        Raises:
            MTQuoteCreateRequestInvalidLines: If ``value`` is neither ``None``
                nor a list.

        Notes:
            **An empty list is allowed.** A quote is composed line by line and
            the first save is usually before any service has been chosen;
            refusing that would make the screen unable to save until it was
            finished. Each line is validated by
            :class:`~models.quoting.quote_line.QuoteLine` itself.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            raise MTQuoteCreateRequestInvalidLines(
                f"Invalid lines: {value!r}. Must be a list or None."
            )
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_quote(self, company_id: str, team_id: str) -> Quote:
        """Build the quote this payload asks for, inside an agency.

        Args:
            company_id (str): The agency the quote belongs to, taken from the
                caller's credential.
            team_id (str): The team that will deliver the work, decided by
                :meth:`~service.organisation.teams.TeamService.attribute`.

        Returns:
            Quote: A draft quote carrying the payload's three fields.

        Notes:
            - The agency is a parameter rather than a field for the reason in the
              class notes, and the conversion lives here rather than in the route
              so that the one place a payload becomes a quote is the one place
              that has to be read to know what a payload can and cannot set.
            - **The team is a parameter for a stronger reason than the agency.**
              It decides whose week the planner rewrites to deliver this work. A
              payload able to name one could file a household onto another
              manager's queue and commit their assistants to it. It is not
              chosen by the caller at all — it is derived from where the
              household lives and how much each team already carries.
            - The status is left to :class:`~models.quoting.quote.Quote`'s own
              default, which is ``draft``. A quote that arrived already accepted
              would have skipped every step that makes acceptance mean anything.
        """
        return Quote(
            company_id=company_id,
            team_id=team_id,
            reference=self.reference,
            customer_id=self.customer_id,
            lines=list(self.lines),
        )
