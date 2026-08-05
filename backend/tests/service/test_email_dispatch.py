from __future__ import annotations

# Standard library imports
from datetime import date, time
from decimal import Decimal
from email.message import EmailMessage
from io import BytesIO
from typing import List

# Third-party imports
from openpyxl import load_workbook
import pytest

from models.auth.user import User

# First-party imports
from models.configuration.email_config import EmailConfig
from models.enums import ContractType, InterventionStatus, QuoteStatus, UserRole
from models.people.customer import Customer
from models.people.hca import Hca
from models.planning.hca_planning import HcaPlanning
from models.planning.intervention import Intervention
from models.quoting.quote import Quote
from models.quoting.quote_line import QuoteLine
from models.quoting.quote_type_week_aggregate import QuoteTypeWeekAggregate
from service.emails.emails import EmailService
from service.emails.exceptions import (
    MTEmailDeliveryFailed,
    MTEmailNoRecipient,
    MTEmailNotConfigured,
)
from service.utils.formatter import Formatter

ADDRESS = {
    "street": "12 rue de Rivoli",
    "postal_code": "75004",
    "city": "Paris",
    "latitude": 48.8566,
    "longitude": 2.3522,
}


def _customer(customer_id: str = "customer-1") -> Customer:
    """Build a customer.

    Args:
        customer_id (str): The identifier to assign.

    Returns:
        Customer: The customer.
    """
    return Customer(
        id=customer_id,
        first_name="Marie",
        last_name="Durand",
        phone_number="+33612345678",
        email=f"{customer_id}@example.com",
        address=ADDRESS,
    )


def _hca(hca_id: str = "hca-1") -> Hca:
    """Build an assistant.

    Args:
        hca_id (str): The identifier to assign.

    Returns:
        Hca: The assistant.
    """
    return Hca(
        id=hca_id,
        first_name="Alice",
        last_name="Martin",
        phone_number="+33612345679",
        email=f"{hca_id}@example.com",
        address=ADDRESS,
        contract_type=ContractType.CDI,
    )


def _planning(interventions: int = 2) -> HcaPlanning:
    """Build a diary carrying a number of visits.

    Args:
        interventions (int): How many visits to place.

    Returns:
        HcaPlanning: The diary.
    """
    return HcaPlanning(
        hca_id="hca-1",
        hca_full_name="Alice Martin",
        period_start=date(2026, 8, 3),
        period_end=date(2026, 8, 9),
        interventions=[
            Intervention(
                name=f"Toilette {index}",
                intervention_type_id="type-1",
                quote_line_id=f"line-{index}",
                hca_id="hca-1",
                hca_full_name="Alice Martin",
                customer_id="customer-1",
                day=date(2026, 8, 5 - index),
                start_time=time(9 + index, 0),
                end_time=time(10 + index, 0),
                address=ADDRESS,
                status=InterventionStatus.PLANNED,
            )
            for index in range(interventions)
        ],
    )


def _manager(user_id: str = "user-1") -> User:
    """Build a manager account.

    Args:
        user_id (str): The identifier to assign.

    Returns:
        User: The account.
    """
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        full_name="Manager Account",
        role=UserRole.MANAGER,
    )


def _quote() -> Quote:
    """Build a priced, accepted quote.

    Returns:
        Quote: The quote.
    """
    return Quote(
        id="quote-1",
        reference="Q-2026-0001",
        customer_id="customer-1",
        status=QuoteStatus.ACCEPTED,
        lines=[
            QuoteLine(
                id="line-1",
                name="Toilette matin",
                intervention_type_id="type-1",
                service_date=date(2026, 8, 3),
                earliest_start=time(9, 0),
                latest_end=time(13, 0),
                duration_minutes=120,
                hourly_rate_ht=Decimal("31.91"),
                total_ht=Decimal("63.82"),
                vat_amount=Decimal("3.51"),
                total_ttc=Decimal("67.33"),
            )
        ],
        aggregates=[
            QuoteTypeWeekAggregate(
                intervention_type_id="type-1",
                intervention_type_name="Toilette",
                iso_year=2026,
                iso_week=32,
                week_start_date=date(2026, 8, 3),
                line_count=1,
                total_minutes=120,
                total_ht=Decimal("63.82"),
                vat_amount=Decimal("3.51"),
                total_ttc=Decimal("67.33"),
            )
        ],
    )


class TestFormatter:
    """Tests for the Excel documents."""

    def test_a_planning_renders_a_readable_workbook(self) -> None:
        """The bytes open as a spreadsheet, not as a blob."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        assert sheet.title == "Planning"
        assert sheet["A1"].value == "Planning — Alice Martin"
        assert [cell.value for cell in sheet[4]] == list(Formatter.PLANNING_HEADERS)

    def test_the_visits_are_written_in_the_order_they_happen(self) -> None:
        """An assistant works down the sheet, so it must be chronological.

        Notes:
            The fixture places its visits out of order deliberately: the second
            one happens the day before the first.
        """
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        days = [sheet.cell(row=row, column=1).value.date() for row in (5, 6)]
        assert days == sorted(days)

    def test_an_empty_planning_says_so(self) -> None:
        """Nothing scheduled is a message, not a blank sheet."""
        sheet = load_workbook(
            BytesIO(Formatter.format_planning(_planning(interventions=0)))
        ).active
        assert sheet["A5"].value == "No intervention scheduled."

    def test_a_quote_renders_its_lines_and_total(self) -> None:
        """Every line and the total reach the sheet."""
        sheet = load_workbook(
            BytesIO(Formatter.format_quote(_quote(), _customer()))
        ).active
        assert sheet["A1"].value == "Quote Q-2026-0001"
        assert sheet["A2"].value == "Marie Durand"
        assert sheet.cell(row=8, column=2).value == "Toilette matin"
        assert sheet.cell(row=10, column=9).value == pytest.approx(67.33)

    def test_an_unpriced_line_leaves_its_cells_empty(self) -> None:
        """Empty reads as "not priced yet"; a zero would read as "free"."""
        quote = _quote()
        quote.lines[0].total_ht = None
        quote.lines[0].total_ttc = None
        sheet = load_workbook(
            BytesIO(Formatter.format_quote(quote, _customer()))
        ).active
        assert sheet.cell(row=8, column=7).value is None
        assert sheet.cell(row=8, column=9).value is None

    def test_amounts_are_numbers_not_strings(self) -> None:
        """A column of amounts must be summable by whoever opens it."""
        sheet = load_workbook(
            BytesIO(Formatter.format_quote(_quote(), _customer()))
        ).active
        cell = sheet.cell(row=8, column=7)
        assert isinstance(cell.value, float)
        assert "€" in cell.number_format

    def test_every_method_is_static(self) -> None:
        """The formatter is a namespace, and is asked to stay one."""
        for name in ("format_planning", "format_quote"):
            attribute = Formatter.__dict__[name]
            assert isinstance(attribute, staticmethod)


class TestEmailService:
    """Tests for the delivery itself."""

    @pytest.fixture
    def sent(self, monkeypatch: pytest.MonkeyPatch) -> List[EmailMessage]:
        """Capture the messages instead of opening an SMTP connection.

        Args:
            monkeypatch (pytest.MonkeyPatch): Used to replace the delivery.

        Returns:
            List[EmailMessage]: The messages the service tried to send.
        """
        captured: List[EmailMessage] = []
        monkeypatch.setattr(
            EmailService, "_deliver", lambda self, message: captured.append(message)
        )
        monkeypatch.setenv("SMTP_USERNAME", "planner")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")
        return captured

    @pytest.fixture
    def service(self) -> EmailService:
        """Return a service with outbound email switched on.

        Returns:
            EmailService: The service under test.
        """
        return EmailService(config=EmailConfig(enabled=True))

    async def test_a_planning_is_sent_to_the_assistant(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """The assistant's own stored address receives their diary."""
        await service.send_planning(_planning(), _hca())
        assert len(sent) == 1
        assert sent[0]["To"] == "hca-1@example.com"
        assert "planning" in sent[0]["Subject"].lower()

    async def test_a_planning_travels_as_a_spreadsheet(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """The document is attached, and it is a real workbook."""
        await service.send_planning(_planning(), _hca())
        attachment = next(sent[0].iter_attachments())
        assert attachment.get_filename().endswith(".xlsx")
        assert load_workbook(BytesIO(attachment.get_payload(decode=True))).active

    async def test_a_quote_is_sent_to_the_customer(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """The customer's own stored address receives their quote."""
        await service.send_quote(_quote(), _customer())
        assert sent[0]["To"] == "customer-1@example.com"
        assert "Q-2026-0001" in sent[0]["Subject"]

    async def test_a_disabled_mailbox_refuses_rather_than_pretends(
        self, sent: List[EmailMessage]
    ) -> None:
        """A planning nobody was sent must not look like one that was."""
        service = EmailService(config=EmailConfig(enabled=False))
        with pytest.raises(MTEmailNotConfigured):
            await service.send_planning(_planning(), _hca())
        assert sent == []

    async def test_missing_credentials_refuse_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Enabled but unconfigured is still not sendable."""
        monkeypatch.delenv("SMTP_USERNAME", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        service = EmailService(config=EmailConfig(enabled=True))
        with pytest.raises(MTEmailNotConfigured):
            await service.send_quote(_quote(), _customer())

    async def test_an_smtp_failure_is_reported(
        self, service: EmailService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A refused conversation surfaces as the service's own exception."""
        monkeypatch.setenv("SMTP_USERNAME", "planner")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")

        def _explode(self: EmailService, message: EmailMessage) -> None:
            raise OSError("connection refused")

        monkeypatch.setattr(EmailService, "_deliver", _explode)
        with pytest.raises(MTEmailDeliveryFailed):
            await service.send_planning(_planning(), _hca())

    async def test_one_bounced_assistant_does_not_stop_the_others(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """A run covers the workforce; one bad address must not cost the rest.

        Notes:
            The second assistant is built without an email address, which is
            what a bounced recipient looks like from here.
        """
        first, second = _hca("hca-1"), _hca("hca-2")
        plannings = [_planning(), _planning().model_copy(update={"hca_id": "hca-2"})]
        object.__setattr__(second, "email", "")
        delivered = await service.send_plannings(plannings, [first, second])
        assert delivered == 1
        assert len(sent) == 1

    async def test_a_planning_without_an_assistant_is_skipped(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """A diary whose assistant is gone has nobody to send to."""
        delivered = await service.send_plannings([_planning()], [])
        assert delivered == 0
        assert sent == []

    async def test_an_empty_recipient_is_refused(self, service: EmailService) -> None:
        """A message with nowhere to go is an error, not a silent no-op."""
        assistant = _hca()
        object.__setattr__(assistant, "email", "")
        with pytest.raises(MTEmailNoRecipient):
            await service.send_planning(_planning(), assistant)

    async def test_quotes_reach_their_own_customers(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """Each quote goes to the customer it names, and no other."""
        delivered = await service.send_quotes(
            [_quote()], [_customer("customer-9"), _customer("customer-1")]
        )
        assert delivered == 1
        assert sent[0]["To"] == "customer-1@example.com"


class TestTeamWorkbook:
    """Tests for the manager's consolidated document."""

    def test_each_assistant_gets_their_own_sheet(self) -> None:
        """A manager reads one round at a time; sheet tabs are the index."""
        plannings = [
            _planning().model_copy(
                update={"hca_id": "hca-1", "hca_full_name": "Alice Martin"}
            ),
            _planning().model_copy(
                update={"hca_id": "hca-2", "hca_full_name": "Bruno Petit"}
            ),
        ]
        workbook = load_workbook(BytesIO(Formatter.format_plannings(plannings)))
        assert workbook.sheetnames == ["Alice Martin", "Bruno Petit"]

    def test_the_sheets_are_ordered_by_name(self) -> None:
        """The same workbook two weeks running has its tabs in one order."""
        plannings = [
            _planning().model_copy(update={"hca_id": "b", "hca_full_name": "Zoe"}),
            _planning().model_copy(update={"hca_id": "a", "hca_full_name": "Ana"}),
        ]
        workbook = load_workbook(BytesIO(Formatter.format_plannings(plannings)))
        assert workbook.sheetnames == ["Ana", "Zoe"]

    def test_a_forbidden_character_does_not_break_the_workbook(self) -> None:
        """Excel refuses five characters in a sheet name; a name may carry them."""
        plannings = [
            _planning().model_copy(
                update={"hca_id": "hca-1", "hca_full_name": "Ana/Bea [test]"}
            )
        ]
        workbook = load_workbook(BytesIO(Formatter.format_plannings(plannings)))
        assert workbook.sheetnames == ["Ana Bea  test"]

    def test_two_assistants_sharing_a_name_keep_two_sheets(self) -> None:
        """A collision must not silently drop somebody's round."""
        plannings = [
            _planning().model_copy(update={"hca_id": "a", "hca_full_name": "Ana Roy"}),
            _planning().model_copy(update={"hca_id": "b", "hca_full_name": "Ana Roy"}),
        ]
        workbook = load_workbook(BytesIO(Formatter.format_plannings(plannings)))
        assert len(workbook.sheetnames) == 2

    def test_a_sheet_carries_that_assistants_visits(self) -> None:
        """Every sheet is the assistant's own week, laid out the same way."""
        plannings = [
            _planning().model_copy(
                update={"hca_id": "hca-1", "hca_full_name": "Alice Martin"}
            )
        ]
        sheet = load_workbook(BytesIO(Formatter.format_plannings(plannings)))[
            "Alice Martin"
        ]
        assert sheet["A1"].value == "Planning — Alice Martin"
        assert [cell.value for cell in sheet[4]] == list(Formatter.PLANNING_HEADERS)

    def test_the_week_is_named_on_every_sheet(self) -> None:
        """Both documents say which week they are, so neither can be misfiled."""
        single = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        assert single["A2"].value.startswith("Week 32 of 2026")


class TestWeeklyDispatch:
    """Tests for cutting a run's period into weeks."""

    @pytest.fixture
    def sent(self, monkeypatch: pytest.MonkeyPatch) -> List[EmailMessage]:
        """Capture the messages instead of opening an SMTP connection.

        Args:
            monkeypatch (pytest.MonkeyPatch): Used to replace the delivery.

        Returns:
            List[EmailMessage]: The messages the service tried to send.
        """
        captured: List[EmailMessage] = []
        monkeypatch.setattr(
            EmailService, "_deliver", lambda self, message: captured.append(message)
        )
        monkeypatch.setenv("SMTP_USERNAME", "planner")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")
        return captured

    @pytest.fixture
    def service(self) -> EmailService:
        """Return a service with outbound email switched on.

        Returns:
            EmailService: The service under test.
        """
        return EmailService(config=EmailConfig(enabled=True))

    async def test_a_fortnight_is_sent_as_two_weeks(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """A run planned over two weeks produces two documents, not one.

        Notes:
            The period runs Monday 3 August to Sunday 16 August — two ISO
            weeks — with one visit in each.
        """
        planning = _planning(interventions=0).model_copy(
            update={
                "period_start": date(2026, 8, 3),
                "period_end": date(2026, 8, 16),
                "interventions": [
                    _planning()
                    .interventions[0]
                    .model_copy(update={"day": date(2026, 8, 4)}),
                    _planning()
                    .interventions[0]
                    .model_copy(update={"day": date(2026, 8, 11)}),
                ],
            }
        )
        delivered = await service.send_plannings([planning], [_hca()])
        assert delivered == 2
        subjects = sorted(message["Subject"] for message in sent)
        assert subjects == [
            "Your planning, 2026-08-03 to 2026-08-09",
            "Your planning, 2026-08-10 to 2026-08-16",
        ]

    async def test_each_week_carries_only_its_own_visits(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """A visit must appear in exactly one week's document."""
        planning = _planning(interventions=0).model_copy(
            update={
                "period_start": date(2026, 8, 3),
                "period_end": date(2026, 8, 16),
                "interventions": [
                    _planning()
                    .interventions[0]
                    .model_copy(update={"day": date(2026, 8, 4)}),
                    _planning()
                    .interventions[0]
                    .model_copy(update={"day": date(2026, 8, 11)}),
                ],
            }
        )
        await service.send_plannings([planning], [_hca()])
        rows = []
        for message in sent:
            attachment = next(message.iter_attachments())
            sheet = load_workbook(BytesIO(attachment.get_payload(decode=True))).active
            rows.append(sheet.cell(row=5, column=1).value.date())
        assert sorted(rows) == [date(2026, 8, 4), date(2026, 8, 11)]

    async def test_a_period_starting_midweek_still_starts_on_a_monday(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """Whatever the run was asked for, a document is a Monday-to-Sunday week."""
        planning = _planning().model_copy(
            update={"period_start": date(2026, 8, 5), "period_end": date(2026, 8, 7)}
        )
        await service.send_plannings([planning], [_hca()])
        assert sent[0]["Subject"] == "Your planning, 2026-08-03 to 2026-08-09"

    async def test_the_manager_receives_the_whole_workforce(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """One consolidated workbook per week, one sheet per assistant."""
        plannings = [
            _planning().model_copy(
                update={"hca_id": "hca-1", "hca_full_name": "Alice Martin"}
            ),
            _planning().model_copy(
                update={"hca_id": "hca-2", "hca_full_name": "Bruno Petit"}
            ),
        ]
        assistants = [_hca("hca-1"), _hca("hca-2")]
        delivered = await service.send_plannings(plannings, assistants, [_manager()])
        assert delivered == 3
        team = [m for m in sent if m["To"] == "user-1@example.com"]
        assert len(team) == 1
        attachment = next(team[0].iter_attachments())
        workbook = load_workbook(BytesIO(attachment.get_payload(decode=True)))
        assert workbook.sheetnames == ["Alice Martin", "Bruno Petit"]

    async def test_an_assistant_never_receives_the_team_workbook(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """The two documents are built from different inputs, not filtered.

        Notes:
            An assistant's copy comes from their own diary, so there is no
            arrangement in which a colleague's round can appear in it.
        """
        plannings = [
            _planning().model_copy(
                update={"hca_id": "hca-1", "hca_full_name": "Alice Martin"}
            ),
            _planning().model_copy(
                update={"hca_id": "hca-2", "hca_full_name": "Bruno Petit"}
            ),
        ]
        await service.send_plannings(
            plannings, [_hca("hca-1"), _hca("hca-2")], [_manager()]
        )
        for message in sent:
            if message["To"] == "user-1@example.com":
                continue
            attachment = next(message.iter_attachments())
            workbook = load_workbook(BytesIO(attachment.get_payload(decode=True)))
            assert workbook.sheetnames == ["Planning"]

    async def test_no_manager_means_no_team_email(
        self, service: EmailService, sent: List[EmailMessage]
    ) -> None:
        """The consolidated copy is sent to managers, or to nobody."""
        delivered = await service.send_plannings([_planning()], [_hca()])
        assert delivered == 1
        assert all(message["To"] == "hca-1@example.com" for message in sent)


class TestWorkbookStyling:
    """Tests for the documents looking like documents.

    Notes:
        These pin the *decisions*, not every colour: that a header is filled
        and legible, that a status is colour-coded, that rows alternate, that
        the header stays put when a long week is scrolled or printed. A
        workbook that quietly loses them still opens, still holds the right
        numbers, and looks like a dump.
    """

    def test_the_title_sits_in_a_filled_band(self) -> None:
        """The first thing a reader sees is a title, not a bare cell."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        assert sheet["A1"].fill.fgColor.rgb == Formatter.TITLE_FILL
        assert sheet["A1"].font.bold is True
        assert sheet["A1"].font.color.rgb == "FFFFFFFF"

    def test_the_title_spans_the_table(self) -> None:
        """A band that stops after one column reads as a stray cell."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        spans = {str(cells) for cells in sheet.merged_cells.ranges}
        assert "A1:G1" in spans

    def test_the_header_row_is_legible_on_its_fill(self) -> None:
        """White on navy, not black on navy."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        header = sheet.cell(row=4, column=1)
        assert header.fill.fgColor.rgb == Formatter.HEADER_FILL
        assert header.font.color.rgb == "FFFFFFFF"
        assert header.font.bold is True

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            pytest.param(InterventionStatus.PLANNED, "FFDDEBF7", id="planned is blue"),
            pytest.param(
                InterventionStatus.CONFIRMED, "FFE2EFDA", id="confirmed is green"
            ),
            pytest.param(
                InterventionStatus.CANCELLED, "FFFCE4E4", id="cancelled is red"
            ),
        ],
    )
    def test_a_status_carries_its_own_colour(
        self, status: InterventionStatus, expected: str
    ) -> None:
        """A cancelled visit must not read like a confirmed one at a glance."""
        planning = _planning(interventions=1)
        planning.interventions[0].status = status
        sheet = load_workbook(BytesIO(Formatter.format_planning(planning))).active
        assert sheet.cell(row=5, column=7).fill.fgColor.rgb == expected

    def test_rows_alternate_so_a_long_week_stays_readable(self) -> None:
        """Banding is what keeps the eye on one row across seven columns."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        assert sheet.cell(row=5, column=4).fill.fgColor.rgb != Formatter.BAND_FILL
        assert sheet.cell(row=6, column=4).fill.fgColor.rgb == Formatter.BAND_FILL

    def test_the_cells_are_ruled(self) -> None:
        """A table without lines is a list of words."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        assert sheet.cell(row=5, column=1).border.left.style == "thin"

    def test_the_header_stays_put_when_scrolled_or_printed(self) -> None:
        """A week of visits runs past the fold on screen and on paper."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        assert sheet.freeze_panes == "A5"
        assert sheet.print_title_rows == "$1:$4"
        assert sheet.page_setup.orientation == "landscape"

    def test_the_week_can_be_filtered(self) -> None:
        """A manager looking for one day should not have to read the rest."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        assert sheet.auto_filter.ref == "A4:G6"

    def test_the_total_row_is_set_apart(self) -> None:
        """The figure a reader looks for last must not look like a visit."""
        sheet = load_workbook(BytesIO(Formatter.format_planning(_planning()))).active
        total = sheet.cell(row=7, column=1)
        assert total.value == "Total"
        assert total.fill.fgColor.rgb == Formatter.TOTAL_FILL
        assert total.border.top.style == "double"

    def test_every_sheet_of_the_team_workbook_is_styled(self) -> None:
        """The manager's copy is the same document, not a plainer one."""
        plannings = [
            _planning().model_copy(
                update={"hca_id": "hca-1", "hca_full_name": "Alice Martin"}
            )
        ]
        sheet = load_workbook(BytesIO(Formatter.format_plannings(plannings)))[
            "Alice Martin"
        ]
        assert sheet["A1"].fill.fgColor.rgb == Formatter.TITLE_FILL
        assert sheet.cell(row=4, column=1).fill.fgColor.rgb == Formatter.HEADER_FILL
        assert sheet.sheet_properties.tabColor.rgb == Formatter.TITLE_FILL

    def test_the_quote_status_is_a_colour_coded_pill(self) -> None:
        """Accepted, rejected and expired must be tellable apart at a glance."""
        sheet = load_workbook(
            BytesIO(Formatter.format_quote(_quote(), _customer()))
        ).active
        assert sheet["A4"].value == "Status: accepted"
        assert sheet["A4"].fill.fgColor.rgb == "FFE2EFDA"

    def test_the_quote_status_pill_is_wide_enough_to_read(self) -> None:
        """Written into the date column alone it is clipped to "tatus: acce"."""
        sheet = load_workbook(
            BytesIO(Formatter.format_quote(_quote(), _customer()))
        ).active
        assert "A4:C4" in {str(cells) for cells in sheet.merged_cells.ranges}

    def test_amounts_are_right_aligned(self) -> None:
        """A column of money that does not line up cannot be scanned."""
        sheet = load_workbook(
            BytesIO(Formatter.format_quote(_quote(), _customer()))
        ).active
        assert sheet.cell(row=8, column=9).alignment.horizontal == "right"

    def test_the_quote_total_is_emphasised(self) -> None:
        """The figure the customer is being asked to pay is the point."""
        sheet = load_workbook(
            BytesIO(Formatter.format_quote(_quote(), _customer()))
        ).active
        total = sheet.cell(row=10, column=9)
        assert total.font.bold is True
        assert total.fill.fgColor.rgb == Formatter.TOTAL_FILL
