from __future__ import annotations

# Standard library imports
import asyncio
from datetime import date, timedelta
from email.message import EmailMessage
from logging import Logger, getLogger
import smtplib
from typing import ClassVar, List, Optional, Tuple

from models.auth.user import User

# First-party imports
from models.configuration.email_config import EmailConfig
from models.people.customer import Customer
from models.people.hca import Hca
from models.planning.hca_planning import HcaPlanning
from models.quoting.quote import Quote
from service.emails.exceptions import (
    MTEmailDeliveryFailed,
    MTEmailNoRecipient,
    MTEmailNotConfigured,
)
from service.utils.formatter import Formatter


class EmailService:
    """Sends a computed planning to an assistant and a quote to a customer.

    Attributes:
        SPREADSHEET_TYPE (ClassVar[str]): MIME type of an ``.xlsx`` attachment.
        SPREADSHEET_SUBTYPE (ClassVar[str]): MIME subtype of the same.
        config (EmailConfig): The outbound SMTP settings.
        logger (Logger): Logger for delivery operations.

    Notes:
        - ``smtplib`` is synchronous, so the whole SMTP conversation is
          dispatched to a worker thread. Running it inline would block the
          event loop for as long as the server takes to answer, and this is
          called in a loop — once per assistant, once per customer.
        - The document is built by
          :class:`~service.utils.formatter.Formatter` and attached, never
          inlined. A planning pasted into a message body is unreadable on a
          phone and unusable on a desk; a spreadsheet is both.
        - Nothing here decides *who* gets what. The recipient is the
          assistant's or the customer's own stored address, so an email cannot
          be redirected by anything the caller passes in.
    """

    SPREADSHEET_TYPE: ClassVar[str] = "application"
    SPREADSHEET_SUBTYPE: ClassVar[str] = (
        "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    def __init__(self, config: EmailConfig, logger: Optional[Logger] = None) -> None:
        """Initialize the service.

        Args:
            config (EmailConfig): The outbound SMTP settings.
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after this module.
        """
        self.config = config
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug(
            "EmailService created for %s:%d (enabled=%s, sender=%s).",
            config.host,
            config.port,
            config.enabled,
            config.sender,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_message(
        self,
        recipient: str,
        subject: str,
        body: str,
        filename: str,
        payload: bytes,  # noqa: E501
    ) -> EmailMessage:
        """Build a message carrying one spreadsheet.

        Args:
            recipient (str): Where the message goes.
            subject (str): The subject line.
            body (str): The plain-text body.
            filename (str): Name the attachment is saved under.
            payload (bytes): The workbook itself.

        Returns:
            EmailMessage: The message, ready to hand to the SMTP client.
        """
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.sender
        message["To"] = recipient
        message.set_content(body)
        message.add_attachment(
            payload,
            maintype=self.SPREADSHEET_TYPE,
            subtype=self.SPREADSHEET_SUBTYPE,
            filename=filename,
        )
        self.logger.debug(
            "Built %r for %s with a %d-byte attachment named %s.",
            subject,
            recipient,
            len(payload),
            filename,
        )
        return message

    def _deliver(self, message: EmailMessage) -> None:
        """Open an SMTP connection and send one message.

        Args:
            message (EmailMessage): The message to send.

        Raises:
            smtplib.SMTPException: If the server refuses the conversation.
            OSError: If the connection itself fails.

        Notes:
            Blocking on purpose — the caller runs this in a worker thread.
        """
        with smtplib.SMTP(
            self.config.host, self.config.port, timeout=self.config.timeout_seconds
        ) as client:
            if self.config.use_tls:
                client.starttls()
            client.login(self.config.get_username(), self.config.get_password())
            client.send_message(message)

    async def _send(
        self,
        recipient: str,
        subject: str,
        body: str,
        filename: str,
        payload: bytes,  # noqa: E501
    ) -> None:
        """Send one message, or explain why it could not be sent.

        Args:
            recipient (str): Where the message goes.
            subject (str): The subject line.
            body (str): The plain-text body.
            filename (str): Name the attachment is saved under.
            payload (bytes): The workbook itself.

        Raises:
            MTEmailNotConfigured: If outbound email is disabled or the
                credentials are absent from the environment.
            MTEmailNoRecipient: If ``recipient`` is empty.
            MTEmailDeliveryFailed: If the SMTP conversation fails.
        """
        if not recipient:
            self.logger.warning("Refusing to send %r: no recipient address.", subject)  # noqa: E501
            raise MTEmailNoRecipient(f"No recipient address for {subject!r}.")
        if not self.config.is_ready():
            self.logger.warning(
                "Not sending %r to %s: outbound email is disabled or has no "
                "credentials.",
                subject,
                recipient,
            )
            raise MTEmailNotConfigured(
                "Outbound email is disabled or its credentials are not set."
            )
        message = self._build_message(recipient, subject, body, filename, payload)  # noqa: E501
        try:
            await asyncio.to_thread(self._deliver, message)
        except (smtplib.SMTPException, OSError) as exc:
            self.logger.error("Could not deliver %r to %s: %s", subject, recipient, exc)  # noqa: E501
            raise MTEmailDeliveryFailed(
                f"Could not deliver {subject!r} to {recipient}."
            ) from exc
        self.logger.info("Delivered %r to %s.", subject, recipient)

    def _weeks_of(self, plannings: List[HcaPlanning]) -> List[Tuple[date, date]]:  # noqa: E501
        """Return the ISO weeks a set of diaries covers, in order.

        Args:
            plannings (List[HcaPlanning]): The diaries to inspect.

        Returns:
            List[Tuple[date, date]]: Each week as its Monday and its Sunday.

        Notes:
            A run may be asked to plan any period — a fortnight, a month — but
            what an assistant works from and what a manager reviews is a week.
            The period is therefore cut on ISO week boundaries rather than on
            the run's own dates, so every document starts on a Monday whatever
            the run was asked for.
        """
        weeks: List[Tuple[date, date]] = []
        for planning in plannings:
            monday = planning.period_start - timedelta(
                days=planning.period_start.weekday()
            )
            while monday <= planning.period_end:
                bounds = (monday, monday + timedelta(days=6))
                if bounds not in weeks:
                    weeks.append(bounds)
                monday = monday + timedelta(days=7)
        weeks.sort()
        self.logger.debug("The plannings cover %d week(s).", len(weeks))
        return weeks

    def _week_of(
        self, planning: HcaPlanning, monday: date, sunday: date
    ) -> HcaPlanning:
        """Return one assistant's diary narrowed to a single week.

        Args:
            planning (HcaPlanning): The diary to narrow.
            monday (date): First day of the week, inclusive.
            sunday (date): Last day of the week, inclusive.

        Returns:
            HcaPlanning: A copy carrying only that week's visits.

        Notes:
            A copy, never a mutation: the caller's diary is also what the API
            answers with, and narrowing it in place would quietly shrink
            somebody else's response.
        """
        return planning.model_copy(
            update={
                "period_start": monday,
                "period_end": sunday,
                "interventions": [
                    visit
                    for visit in planning.interventions
                    if monday <= visit.day <= sunday
                ],
            }
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    async def send_planning(self, planning: HcaPlanning, assistant: Hca) -> None:  # noqa: E501
        """Send an assistant their computed planning as a spreadsheet.

        Args:
            planning (HcaPlanning): The diary that was computed.
            assistant (Hca): The assistant it belongs to; supplies the address.

        Raises:
            MTEmailNotConfigured: If outbound email is not usable.
            MTEmailNoRecipient: If the assistant has no email address.
            MTEmailDeliveryFailed: If the SMTP conversation fails.

        Notes:
            An empty planning is still sent. "Nothing was assigned to you this
            week" is information an assistant needs, and its absence would be
            indistinguishable from an email that failed to arrive.
        """
        self.logger.info(
            "Emailing the %s–%s planning of assistant %s.",
            planning.period_start,
            planning.period_end,
            planning.hca_id,
        )
        await self._send(
            recipient=str(assistant.email),
            subject=(
                f"Your planning, {planning.period_start} to {planning.period_end}"
            ),
            body=(
                f"Hello {planning.hca_full_name},\n\n"
                f"Your planning for {planning.period_start} to "
                f"{planning.period_end} is attached; it lists "
                f"{len(planning.interventions)} intervention(s).\n\n"
                f"This message was sent automatically when the planning was "
                f"computed.\n"
            ),
            filename=f"planning-{planning.hca_id}-{planning.period_start}.xlsx",
            payload=Formatter.format_planning(planning),
        )

    async def send_quote(self, quote: Quote, customer: Customer) -> None:
        """Send a customer their quote as a spreadsheet.

        Args:
            quote (Quote): The quote to send.
            customer (Customer): The customer it is addressed to; supplies the
                address.

        Raises:
            MTEmailNotConfigured: If outbound email is not usable.
            MTEmailNoRecipient: If the customer has no email address.
            MTEmailDeliveryFailed: If the SMTP conversation fails.
        """
        self.logger.info(
            "Emailing quote %s to customer %s.", quote.reference, customer.id
        )
        await self._send(
            recipient=str(customer.email),
            subject=f"Your quote {quote.reference}",
            body=(
                f"Hello {customer.full_name()},\n\n"
                f"Quote {quote.reference} is attached, totalling "
                f"{quote.total_ttc()} € including VAT.\n\n"
                f"This message was sent automatically.\n"
            ),
            filename=f"quote-{quote.reference}.xlsx",
            payload=Formatter.format_quote(quote, customer),
        )

    async def send_team_planning(
        self, plannings: List[HcaPlanning], recipient: User
    ) -> None:
        """Send a manager the whole workforce's week, one sheet per assistant.

        Args:
            plannings (List[HcaPlanning]): Every assistant's week.
            recipient (User): The manager or administrator receiving it.

        Raises:
            MTEmailNotConfigured: If outbound email is not usable.
            MTEmailNoRecipient: If the account has no email address.
            MTEmailDeliveryFailed: If the SMTP conversation fails.

        Notes:
            Sent to managers and administrators only. The document holds every
            assistant's round, which is exactly what an assistant must not
            receive — their own copy is a different document, built from a
            single diary.
        """
        first = plannings[0] if plannings else None
        period = (
            f"{first.period_start} to {first.period_end}" if first else "the period"
        )
        self.logger.info(
            "Emailing the team planning (%d assistant(s), %s) to %s.",
            len(plannings),
            period,
            recipient.id,
        )
        await self._send(
            recipient=str(recipient.email),
            subject=f"Team planning, {period}",
            body=(
                f"Hello {recipient.full_name},\n\n"
                f"The planning for {period} is attached, with one sheet per "
                f"assistant ({len(plannings)} in total).\n\n"
                f"This message was sent automatically when the planning was "
                f"computed.\n"
            ),
            filename=(
                f"team-planning-{first.period_start}.xlsx"
                if first
                else "team-planning.xlsx"
            ),
            payload=Formatter.format_plannings(plannings),
        )

    async def send_plannings(
        self,  # noqa: E501
        plannings: List[HcaPlanning],
        assistants: List[Hca],
        managers: Optional[List[User]] = None,
    ) -> int:  # noqa: E501
        """Send each week of a computed run to everyone entitled to it.

        Args:
            plannings (List[HcaPlanning]): The diaries that were computed.
            assistants (List[Hca]): The assistants they belong to.
            managers (Optional[List[User]]): The managers and administrators
                who receive the consolidated copy. ``None`` sends none.

        Returns:
            int: How many messages were delivered, both kinds counted.

        Notes:
            - **A week at a time.** A run planned over a fortnight produces two
              rounds of emails, each covering one Monday-to-Sunday week, rather
              than one document nobody can read at a glance.
            - **Two audiences, two documents.** An assistant receives their own
              week and nothing else; a manager receives every assistant's week,
              a sheet each. Neither is a filtered view of the other — the
              assistant's copy is built from a single diary, so there is no
              arrangement in which somebody else's round can reach it.
            - One failure does not stop the rest. An assistant whose mailbox
              bounces must not cost everybody else their schedule, so each
              delivery is attempted and counted on its own.
        """
        by_id = {assistant.id: assistant for assistant in assistants}
        recipients = managers if managers else []
        delivered = 0
        for monday, sunday in self._weeks_of(plannings):
            weekly = [self._week_of(planning, monday, sunday) for planning in plannings]
            self.logger.info(
                "Dispatching the week of %s to %s: %d assistant(s), %d manager(s).",
                monday,
                sunday,
                len(weekly),
                len(recipients),
            )
            for planning in weekly:
                assistant = by_id.get(planning.hca_id)
                if assistant is None:
                    self.logger.warning(
                        "No assistant record for planning %s; skipping it.",
                        planning.hca_id,
                    )
                    continue
                try:
                    await self.send_planning(planning, assistant)
                except (
                    MTEmailDeliveryFailed,
                    MTEmailNoRecipient,
                    MTEmailNotConfigured,
                ) as exc:
                    self.logger.error(
                        "Planning for assistant %s not delivered: %s",
                        planning.hca_id,
                        exc,
                    )
                    continue
                delivered += 1
            for manager in recipients:
                try:
                    await self.send_team_planning(weekly, manager)
                except (
                    MTEmailDeliveryFailed,
                    MTEmailNoRecipient,
                    MTEmailNotConfigured,
                ) as exc:
                    self.logger.error(
                        "Team planning not delivered to %s: %s", manager.id, exc
                    )
                    continue
                delivered += 1
        self.logger.info("Delivered %d planning message(s).", delivered)
        return delivered

    async def send_quotes(self, quotes: List[Quote], customers: List[Customer]) -> int:
        """Send every customer behind a computed run their quote.

        Args:
            quotes (List[Quote]): The quotes to send.
            customers (List[Customer]): The customers they are addressed to.

        Returns:
            int: How many were delivered.
        """
        by_id = {customer.id: customer for customer in customers}
        delivered = 0
        for quote in quotes:
            customer = by_id.get(quote.customer_id)
            if customer is None:
                self.logger.warning(
                    "No customer record for quote %s; skipping it.", quote.reference
                )
                continue
            try:
                await self.send_quote(quote, customer)
            except (
                MTEmailDeliveryFailed,
                MTEmailNoRecipient,
                MTEmailNotConfigured,
            ) as exc:
                self.logger.error("Quote %s not delivered: %s", quote.reference, exc)
                continue
            delivered += 1
        self.logger.info("Delivered %d of %d quote(s).", delivered, len(quotes))
        return delivered
