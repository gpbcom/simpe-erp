from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# First-party imports
from models.planning.intervention import Intervention
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from service.intervention_types.exceptions import MTInterventionTypeNotFound
from service.planning.exceptions import (
    MTInterventionNotFound,
    MTInterventionNotQuoted,
)
from service.quotes.exceptions import MTQuoteNotFound
from service.quotes.quotes import QuoteService
from storage.repositories.catalog.intervention_type import InterventionTypeRepository
from storage.repositories.planning.intervention import InterventionRepository


class InterventionService:
    """Edits a single scheduled visit, and the quote line behind it.

    Attributes:
        interventions (InterventionRepository): The scheduled visits.
        quotes (QuoteService): Prices and stores the paperwork.
        types (InterventionTypeRepository): The catalog the rates come from.
        logger (Logger): Logger for visit operations.

    Notes:
        - **Every edit here is really an edit to a quote line.** A visit is not
          a record anybody authored. It is what the solver made of a line
          somebody sold. Deleting the visit alone would last until the next
          planning run rebuilt the period from the lines and put it straight
          back, and changing its service alone would bill the customer for work
          nobody is going to do. So each method changes the line first and the
          calendar second.
        - Separate from :class:`~service.planning.plannings.PlanningService`,
          which owns the *solve*. That class already carries the constraint
          model, the solver and the diagnosis; giving it the paperwork as well
          would make the one class in the backend that nobody dares open.
    """

    def __init__(
        self,
        interventions: InterventionRepository,
        quotes: QuoteService,
        types: InterventionTypeRepository,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the service.

        Args:
            interventions (InterventionRepository): The scheduled visits.
            quotes (QuoteService): Prices and stores the paperwork.
            types (InterventionTypeRepository): The catalog the rates come
                from.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.interventions = interventions
        self.quotes = quotes
        self.types = types
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("InterventionService created.")

    ############################
    # Internal Helpers Methods #
    ############################

    async def _get(self, intervention_id: str) -> Intervention:
        """Return a visit, or refuse.

        Args:
            intervention_id (str): The visit wanted.

        Returns:
            Intervention: The visit.

        Raises:
            MTInterventionNotFound: If no such visit exists.
        """
        found = await self.interventions.get(intervention_id)
        if found is None:
            self.logger.warning(
                "Refused an edit to intervention %s: it does not exist.",
                intervention_id,
            )
            raise MTInterventionNotFound(f"No intervention {intervention_id!r} exists.")
        return found

    async def _quote_of(self, intervention: Intervention) -> Quote:
        """Return the quote a visit was sold on, or refuse.

        Args:
            intervention (Intervention): The visit whose paperwork is wanted.

        Returns:
            Quote: The quote carrying the visit's line.

        Raises:
            MTInterventionNotQuoted: If the line no longer exists.
        """
        try:
            return await self.quotes.get_by_line(intervention.quote_line_id)
        except MTQuoteNotFound:
            self.logger.error(
                "Intervention %s names line %s, which no quote carries.",
                intervention.id,
                intervention.quote_line_id,
            )
            raise MTInterventionNotQuoted(
                f"The line intervention {intervention.id!r} was scheduled from "
                f"no longer exists. It cannot be edited from the calendar."
            ) from None

    def _line_of(self, quote: Quote, line_id: str) -> QuoteLine:
        """Return one line of a quote, or refuse.

        Args:
            quote (Quote): The quote to look in.
            line_id (str): The line wanted.

        Returns:
            QuoteLine: The line.

        Raises:
            MTInterventionNotQuoted: If the quote does not carry it.
        """
        for line in quote.lines:
            if line.id == line_id:
                return line
        self.logger.error(
            "Quote %s does not carry the line %s it was looked up by.",
            quote.reference,
            line_id,
        )
        raise MTInterventionNotQuoted(
            f"Quote {quote.reference!r} does not carry a line {line_id!r}."
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def delete(self, intervention_id: str) -> Tuple[str, Optional[Quote]]:  # noqa: E501
        """Cancel a visit, and take it off the quote it was sold on.

        Args:
            intervention_id (str): The visit to cancel.

        Returns:
            Tuple[str, Optional[Quote]]: The team whose calendar the visit was
            on, and the repriced quote — ``None`` when that visit was the only
            thing on it and the quote went with it.

        Raises:
            MTInterventionNotFound: If no such visit exists.
            MTInterventionNotQuoted: If its line no longer exists.
            MTQuoteNotEditable: If the quote refuses the edit.

        Notes:
            - **The line goes, not just the visit.** The next planning run
              rebuilds the period from the quote lines, so a visit removed on
              its own reappears within the hour, and nobody would connect the
              two.
            - A quote whose last line is removed is **deleted** rather than
              left standing empty. An empty quote cannot be priced, cannot be
              validated and cannot be printed. Keeping the header would leave a
              record whose only future is an error message.
            - **The team comes back with the quote**, and it is read from the
              visit before anything is removed. A cancellation ends in a replan
              of one team's week, and once the row is gone there is nothing left
              to ask whose week it was — the quote cannot answer either, because
              the last-line case deletes it.
        """
        intervention = await self._get(intervention_id)
        quote = await self._quote_of(intervention)
        self._line_of(quote, intervention.quote_line_id)
        remaining: List[QuoteLine] = [
            line for line in quote.lines if line.id != intervention.quote_line_id
        ]
        self.logger.info(
            "Cancelling intervention %s (%s on %s) and its line on quote %s.",
            intervention_id,
            intervention.name,
            intervention.day,
            quote.reference,
        )
        await self.interventions.delete(intervention_id)
        if not remaining:
            self.logger.warning(
                "Quote %s has no line left and is deleted with its last visit.",
                quote.reference,
            )
            await self.quotes.delete(quote.id or "")
            return intervention.team_id, None
        return intervention.team_id, await self.quotes.replace_lines(
            quote.id or "", remaining
        )

    async def change_type(
        self, intervention_id: str, intervention_type_id: str
    ) -> Quote:
        """Sell a visit as a different service, and reprice the quote.

        Args:
            intervention_id (str): The visit to re-classify.
            intervention_type_id (str): The catalog entry it should be sold as.

        Returns:
            Quote: The repriced quote.

        Raises:
            MTInterventionNotFound: If no such visit exists.
            MTInterventionNotQuoted: If its line no longer exists.
            MTInterventionTypeNotFound: If the catalog has no such entry.
            MTQuoteNotEditable: If the quote refuses the edit.

        Notes:
            - **The VAT category follows the catalog entry**, exactly as it
              does when the quote is written: the entry's category is what this
              service usually is. It stays editable on the quote itself, which
              is where somebody who knows whether *this customer's* hours fall
              under a care plan does that work.
            - The visit's label follows the type only when nobody had written
              their own. A manager who typed "Toilette — étage" keeps it. A
              line still carrying the catalog wording gets the new wording,
              rather than a calendar block that names the service it used to
              be.
        """
        intervention = await self._get(intervention_id)
        chosen = await self.types.get(intervention_type_id)
        if chosen is None:
            self.logger.warning(
                "Refused to re-classify intervention %s: no type %s exists.",
                intervention_id,
                intervention_type_id,
            )
            raise MTInterventionTypeNotFound(
                f"No intervention type {intervention_type_id!r} exists."
            )
        quote = await self._quote_of(intervention)
        line = self._line_of(quote, intervention.quote_line_id)
        previous = await self.types.get(line.intervention_type_id)
        renaming = previous is not None and line.name == previous.name
        self.logger.info(
            "Re-classifying intervention %s from %s to %s on quote %s.",
            intervention_id,
            line.intervention_type_id,
            intervention_type_id,
            quote.reference,
        )
        updated = line.model_copy(
            update={
                "intervention_type_id": intervention_type_id,
                "service_category": chosen.service_category,
                "name": chosen.name if renaming else line.name,
            }
        )
        lines = [
            updated if entry.id == intervention.quote_line_id else entry
            for entry in quote.lines
        ]
        repriced = await self.quotes.replace_lines(quote.id or "", lines)
        await self.interventions.update(
            intervention.model_copy(
                update={
                    "intervention_type_id": intervention_type_id,
                    "name": updated.name,
                }
            )
        )
        return repriced
