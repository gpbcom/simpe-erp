from __future__ import annotations

# Standard library imports
from io import BytesIO
from logging import getLogger
from typing import ClassVar, Dict, List, Tuple

# Third-party imports
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet

# First-party imports
from models.people.customer import Customer
from models.planning.hca_planning import HcaPlanning
from models.quoting.quote import Quote


class Formatter:
    """Renders a quote or a planning as an Excel workbook.

    Attributes:
        PLANNING_HEADERS (ClassVar[Tuple[str, ...]]): Column titles of a
            planning sheet.
        QUOTE_HEADERS (ClassVar[Tuple[str, ...]]): Column titles of a quote's
            line sheet.
        HEADER_FILL (ClassVar[str]): Background colour of the header row.
        DATE_FORMAT (ClassVar[str]): How a day is written in a cell.
        MONEY_FORMAT (ClassVar[str]): How an amount is written in a cell.

    Notes:
        - Every method is static, and deliberately: formatting is a pure
          function of what it is handed. There is nothing to configure, nothing
          to inject and nothing to remember between two calls, so an instance
          would carry no state and only invite one to be added later.
        - Excel rather than CSV because both documents are read by people, not
          parsed: an assistant reads their week on a phone, a customer reads
          amounts they are being asked to pay. Column widths, a frozen header
          and real date and currency cells are the difference between a
          document and a dump.
        - Amounts are written as **numbers with a currency format**, never as
          pre-formatted strings. A string cannot be summed, and the first
          thing anyone does with a quote is add up a column.
    """

    PLANNING_HEADERS: ClassVar[Tuple[str, ...]] = (
        "Day",
        "Start",
        "End",
        "Service",
        "Customer",
        "Address",
        "Status",
    )
    QUOTE_HEADERS: ClassVar[Tuple[str, ...]] = (
        "Date",
        "Service",
        "From",
        "To",
        "Duration (min)",
        "Hourly rate (excl. VAT)",
        "Total (excl. VAT)",
        "VAT",
        "Total (incl. VAT)",
    )
    TITLE_FILL: ClassVar[str] = "FF1F3864"
    HEADER_FILL: ClassVar[str] = "FF2F5597"
    SUBTITLE_FILL: ClassVar[str] = "FFEDF2F9"
    BAND_FILL: ClassVar[str] = "FFEEF3FA"
    TOTAL_FILL: ClassVar[str] = "FFDDE5F0"
    GRID_COLOUR: ClassVar[str] = "FFD6DCE4"
    MUTED_TEXT: ClassVar[str] = "FF4A5568"
    STATUS_COLOURS: ClassVar[Dict[str, Tuple[str, str]]] = {
        "planned": ("FFDDEBF7", "FF1F4E79"),
        "confirmed": ("FFE2EFDA", "FF375623"),
        "completed": ("FFEDEDED", "FF3F3F3F"),
        "cancelled": ("FFFCE4E4", "FF9C0006"),
        "draft": ("FFEDEDED", "FF3F3F3F"),
        "sent": ("FFDDEBF7", "FF1F4E79"),
        "accepted": ("FFE2EFDA", "FF375623"),
        "rejected": ("FFFCE4E4", "FF9C0006"),
        "expired": ("FFFFF2CC", "FF7F6000"),
    }
    MAX_SHEET_TITLE: ClassVar[int] = 31
    FORBIDDEN_SHEET_CHARACTERS: ClassVar[Tuple[str, ...]] = (
        "/",
        "\\",
        "?",
        "*",
        "[",
        "]",
        ":",
    )
    DATE_FORMAT: ClassVar[str] = "yyyy-mm-dd"
    MONEY_FORMAT: ClassVar[str] = '#,##0.00\\ "€"'

    @staticmethod
    def write_planning_sheet(sheet: Worksheet, planning: HcaPlanning) -> None:
        """Lay one assistant's week out on a worksheet.

        Args:
            sheet (Worksheet): The sheet to write on.
            planning (HcaPlanning): The week to render.

        Notes:
            - Shared by both documents, so an assistant's own sheet and their
              page of the team workbook are the same sheet. Two renderers would
              drift, and the first person to notice would be the assistant
              holding the one that is wrong.
            - Interventions are written in the order they happen, not the order
              they were solved in: this is the sheet an assistant works from,
              and a day out of sequence is worse than no sheet at all.
        """
        iso_year, iso_week, _ = planning.period_start.isocalendar()
        columns = len(Formatter.PLANNING_HEADERS)
        last_column = sheet.cell(row=4, column=columns).column_letter

        sheet.merge_cells(f"A1:{last_column}1")
        title = sheet["A1"]
        title.value = f"Planning — {planning.hca_full_name}"
        title.font = Font(bold=True, size=16, color="FFFFFFFF")
        title.fill = PatternFill("solid", fgColor=Formatter.TITLE_FILL)
        title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        sheet.row_dimensions[1].height = 30

        sheet.merge_cells(f"A2:{last_column}2")
        subtitle = sheet["A2"]
        subtitle.value = (
            f"Week {iso_week:02d} of {iso_year} — "
            f"{planning.period_start} to {planning.period_end}"
        )
        subtitle.font = Font(bold=True, color=Formatter.MUTED_TEXT)
        subtitle.fill = PatternFill("solid", fgColor=Formatter.SUBTITLE_FILL)
        subtitle.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        sheet.merge_cells(f"A3:{last_column}3")
        summary = sheet["A3"]
        summary.value = (
            f"{len(planning.interventions)} intervention(s), "
            f"{planning.total_minutes() // 60}h{planning.total_minutes() % 60:02d}"
        )
        summary.font = Font(italic=True, color=Formatter.MUTED_TEXT)
        summary.fill = PatternFill("solid", fgColor=Formatter.SUBTITLE_FILL)
        summary.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        edge = Side(style="thin", color=Formatter.GRID_COLOUR)
        grid = Border(left=edge, right=edge, top=edge, bottom=edge)
        for column, header in enumerate(Formatter.PLANNING_HEADERS, start=1):
            cell = sheet.cell(row=4, column=column, value=header)
            cell.font = Font(bold=True, color="FFFFFFFF")
            cell.fill = PatternFill("solid", fgColor=Formatter.HEADER_FILL)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = grid
        sheet.row_dimensions[4].height = 22

        ordered = sorted(
            planning.interventions, key=lambda item: (item.day, item.start_time)
        )
        band = PatternFill("solid", fgColor=Formatter.BAND_FILL)
        for offset, intervention in enumerate(ordered):
            row = 5 + offset
            sheet.cell(
                row=row, column=1, value=intervention.day
            ).number_format = Formatter.DATE_FORMAT
            sheet.cell(row=row, column=2, value=intervention.start_time.isoformat())
            sheet.cell(row=row, column=3, value=intervention.end_time.isoformat())
            sheet.cell(row=row, column=4, value=intervention.name)
            sheet.cell(row=row, column=5, value=intervention.customer_id)
            sheet.cell(row=row, column=6, value=intervention.address.to_single_line())
            sheet.cell(row=row, column=7, value=intervention.status.value)

            background, text = Formatter.STATUS_COLOURS.get(
                intervention.status.value, (Formatter.BAND_FILL, Formatter.MUTED_TEXT)
            )
            for column in range(1, columns + 1):
                cell = sheet.cell(row=row, column=column)
                cell.border = grid
                if offset % 2:
                    cell.fill = band
                if column in (1, 2, 3):
                    cell.alignment = Alignment(horizontal="center")
            status_cell = sheet.cell(row=row, column=columns)
            status_cell.fill = PatternFill("solid", fgColor=background)
            status_cell.font = Font(bold=True, color=text)
            status_cell.alignment = Alignment(horizontal="center")

        if not ordered:
            empty = sheet.cell(row=5, column=1, value="No intervention scheduled.")
            empty.font = Font(italic=True, color=Formatter.MUTED_TEXT)
            sheet.merge_cells(f"A5:{last_column}5")
            getLogger(__name__).warning(
                "Assistant %s has an empty planning for %s to %s.",
                planning.hca_id,
                planning.period_start,
                planning.period_end,
            )
        else:
            total_row = 5 + len(ordered)
            label = sheet.cell(row=total_row, column=1, value="Total")
            label.font = Font(bold=True)
            hours = sheet.cell(
                row=total_row,
                column=2,
                value=(
                    f"{planning.total_minutes() // 60}h"
                    f"{planning.total_minutes() % 60:02d}"
                ),
            )
            hours.font = Font(bold=True)
            hours.alignment = Alignment(horizontal="center")
            for column in range(1, columns + 1):
                cell = sheet.cell(row=total_row, column=column)
                cell.fill = PatternFill("solid", fgColor=Formatter.TOTAL_FILL)
                cell.border = Border(
                    left=edge,
                    right=edge,
                    bottom=edge,
                    top=Side(style="double", color=Formatter.HEADER_FILL),
                )
            sheet.auto_filter.ref = f"A4:{last_column}{4 + len(ordered)}"

        widths: List[int] = [12, 8, 8, 34, 20, 52, 12]
        for column, width in enumerate(widths, start=1):
            sheet.column_dimensions[
                sheet.cell(row=4, column=column).column_letter
            ].width = width
        sheet.freeze_panes = "A5"
        sheet.sheet_properties.tabColor = Formatter.TITLE_FILL
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.print_title_rows = "1:4"

    @staticmethod
    def format_planning(planning: HcaPlanning) -> bytes:
        """Render one assistant's own week as an Excel workbook.

        Args:
            planning (HcaPlanning): The week to render.

        Returns:
            bytes: The ``.xlsx`` document, ready to attach to an email.

        Notes:
            One sheet, one assistant, one week. This is what an assistant
            receives, and it contains nobody else's visits — the model itself
            only holds one person's, so there is nothing here to filter.
        """
        logger = getLogger(__name__)
        logger.debug(
            "Rendering the week of assistant %s (%s to %s, %d intervention(s)).",
            planning.hca_id,
            planning.period_start,
            planning.period_end,
            len(planning.interventions),
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Planning"
        Formatter.write_planning_sheet(sheet, planning)

        stream = BytesIO()
        workbook.save(stream)
        payload = stream.getvalue()
        logger.info(
            "Rendered a %d-byte planning workbook for assistant %s.",
            len(payload),
            planning.hca_id,
        )
        return payload

    @staticmethod
    def format_plannings(plannings: List[HcaPlanning]) -> bytes:
        """Render the whole workforce's week, one sheet per assistant.

        Args:
            plannings (List[HcaPlanning]): Every assistant's week.

        Returns:
            bytes: The ``.xlsx`` document, ready to attach to an email.

        Notes:
            - This is the manager's copy. A sheet per assistant rather than one
              long sheet with a name column: a manager reads one round at a
              time, and Excel's sheet tabs are the fastest index there is.
            - Sheet names are the assistant's name, trimmed to the 31 characters
              Excel allows and stripped of the five characters it forbids. Two
              assistants who collide after trimming are disambiguated by a
              counter rather than silently overwriting one another.
            - Assistants are ordered by name, so the same workbook two weeks
              running has its tabs in the same places.
        """
        logger = getLogger(__name__)
        logger.info(
            "Rendering a team planning workbook for %d assistant(s).", len(plannings)
        )
        workbook = Workbook()
        workbook.remove(workbook.active)

        ordered = sorted(plannings, key=lambda item: (item.hca_full_name, item.hca_id))
        used: List[str] = []
        for planning in ordered:
            title = planning.hca_full_name
            for forbidden in Formatter.FORBIDDEN_SHEET_CHARACTERS:
                title = title.replace(forbidden, " ")
            title = title.strip()[: Formatter.MAX_SHEET_TITLE] or planning.hca_id
            if title in used:
                suffix = f" ({used.count(title) + 1})"
                title = title[: Formatter.MAX_SHEET_TITLE - len(suffix)] + suffix
            used.append(title)
            Formatter.write_planning_sheet(workbook.create_sheet(title), planning)

        if not ordered:
            sheet = workbook.create_sheet("Planning")
            sheet["A1"] = "No assistant has a planning for this week."
            logger.warning("Rendered a team workbook with no assistant in it.")

        stream = BytesIO()
        workbook.save(stream)
        payload = stream.getvalue()
        logger.info(
            "Rendered a %d-byte team workbook holding %d sheet(s).",
            len(payload),
            len(workbook.sheetnames),
        )
        return payload

    @staticmethod
    def format_quote(quote: Quote, customer: Customer) -> bytes:
        """Render a quote as an Excel workbook.

        Args:
            quote (Quote): The quote to render, priced.
            customer (Customer): The customer it is addressed to.

        Returns:
            bytes: The ``.xlsx`` document, ready to attach to an email.

        Notes:
            An unpriced line is written with empty amount cells rather than
            zeroes. A zero reads as "free"; an empty cell reads as "not priced
            yet", which is what it is.
        """
        logger = getLogger(__name__)
        logger.debug(
            "Rendering quote %s for customer %s (%d line(s)).",
            quote.reference,
            customer.id,
            len(quote.lines),
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Quote"
        columns = len(Formatter.QUOTE_HEADERS)
        last_column = sheet.cell(row=7, column=columns).column_letter
        edge = Side(style="thin", color=Formatter.GRID_COLOUR)
        grid = Border(left=edge, right=edge, top=edge, bottom=edge)

        sheet.merge_cells(f"A1:{last_column}1")
        title = sheet["A1"]
        title.value = f"Quote {quote.reference}"
        title.font = Font(bold=True, size=16, color="FFFFFFFF")
        title.fill = PatternFill("solid", fgColor=Formatter.TITLE_FILL)
        title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        sheet.row_dimensions[1].height = 30

        for row, value in (
            (2, customer.full_name()),
            (3, customer.address.to_single_line()),
        ):
            sheet.merge_cells(f"A{row}:{last_column}{row}")
            cell = sheet.cell(row=row, column=1, value=value)
            cell.fill = PatternFill("solid", fgColor=Formatter.SUBTITLE_FILL)
            cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
            cell.font = Font(bold=row == 2, color=Formatter.MUTED_TEXT)

        status_background, status_text = Formatter.STATUS_COLOURS.get(
            quote.status.value, (Formatter.SUBTITLE_FILL, Formatter.MUTED_TEXT)
        )
        # Merged across three columns: the pill carries a word, and column A is
        # sized for a date. Written into A4 alone it is clipped to "tatus: acce".
        sheet.merge_cells("A4:C4")
        status_cell = sheet.cell(row=4, column=1, value=f"Status: {quote.status.value}")
        status_cell.fill = PatternFill("solid", fgColor=status_background)
        status_cell.font = Font(bold=True, color=status_text)
        status_cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=False
        )
        for column in range(1, 4):
            sheet.cell(row=4, column=column).border = grid
        if quote.valid_until is not None:
            valid = sheet.cell(
                row=5, column=1, value=f"Valid until: {quote.valid_until}"
            )
            valid.font = Font(italic=True, color=Formatter.MUTED_TEXT)

        for column, header in enumerate(Formatter.QUOTE_HEADERS, start=1):
            cell = sheet.cell(row=7, column=column, value=header)
            cell.font = Font(bold=True, color="FFFFFFFF")
            cell.fill = PatternFill("solid", fgColor=Formatter.HEADER_FILL)
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
            cell.border = grid
        sheet.row_dimensions[7].height = 30

        ordered = sorted(quote.lines, key=lambda line: (line.service_date, line.name))
        band = PatternFill("solid", fgColor=Formatter.BAND_FILL)
        for offset, line in enumerate(ordered):
            row = 8 + offset
            sheet.cell(
                row=row, column=1, value=line.service_date
            ).number_format = Formatter.DATE_FORMAT
            sheet.cell(row=row, column=2, value=line.name)
            sheet.cell(row=row, column=3, value=line.earliest_start.isoformat())
            sheet.cell(row=row, column=4, value=line.latest_end.isoformat())
            sheet.cell(row=row, column=5, value=line.duration_minutes)
            for column, amount in enumerate(
                (line.hourly_rate_ht, line.total_ht, line.vat_amount, line.total_ttc),
                start=6,
            ):
                cell = sheet.cell(
                    row=row, column=column, value=float(amount) if amount else None
                )
                cell.number_format = Formatter.MONEY_FORMAT
            for column in range(1, columns + 1):
                cell = sheet.cell(row=row, column=column)
                cell.border = grid
                if offset % 2:
                    cell.fill = band
                if column in (1, 3, 4, 5):
                    cell.alignment = Alignment(horizontal="center")
                if column >= 6:
                    cell.alignment = Alignment(horizontal="right")

        total_row = 8 + len(ordered) + 1
        label = sheet.cell(row=total_row, column=5, value="Total")
        label.font = Font(bold=True, size=12)
        label.alignment = Alignment(horizontal="right")
        for column, amount in enumerate(
            (quote.total_ht(), quote.total_vat(), quote.total_ttc()), start=7
        ):
            cell = sheet.cell(row=total_row, column=column, value=float(amount))
            cell.number_format = Formatter.MONEY_FORMAT
            cell.font = Font(bold=True, size=12)
            cell.alignment = Alignment(horizontal="right")
        for column in range(1, columns + 1):
            cell = sheet.cell(row=total_row, column=column)
            cell.fill = PatternFill("solid", fgColor=Formatter.TOTAL_FILL)
            cell.border = Border(
                left=edge,
                right=edge,
                bottom=edge,
                top=Side(style="double", color=Formatter.HEADER_FILL),
            )

        widths = [12, 34, 8, 8, 14, 22, 18, 12, 18]
        for column, width in enumerate(widths, start=1):
            sheet.column_dimensions[
                sheet.cell(row=7, column=column).column_letter
            ].width = width
        sheet.freeze_panes = "A8"
        sheet.sheet_properties.tabColor = Formatter.TITLE_FILL
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.print_title_rows = "1:7"
        if ordered:
            sheet.auto_filter.ref = f"A7:{last_column}{7 + len(ordered)}"

        stream = BytesIO()
        workbook.save(stream)
        payload = stream.getvalue()
        logger.info(
            "Rendered a %d-byte quote workbook for %s (%s).",
            len(payload),
            quote.reference,
            customer.id,
        )
        return payload
