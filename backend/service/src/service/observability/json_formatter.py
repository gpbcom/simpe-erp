from __future__ import annotations

from datetime import UTC, datetime

# Standard library imports
import json
from logging import Formatter, LogRecord
from typing import ClassVar, Dict, FrozenSet, Optional


class JsonLogFormatter(Formatter):
    """Renders a log record as one JSON object on one line.

    Attributes:
        RESERVED (ClassVar[FrozenSet[str]]): The attributes every record carries
            for the logging machinery's own use, which are not context.
        CARRIED (ClassVar[Dict[str, str]]): Record attributes copied into the
            object under a different name.

    Notes:
        - **One line per record, and never more.** A log pipeline splits on
          newlines, so a formatter that let one through would turn a single
          traceback into eight unrelated entries — seven of them unparseable,
          and the one carrying the message not the one carrying the stack.
          ``json.dumps`` escapes them. The exception text is a *field*.
        - **Anything a caller attached with ``extra=`` becomes a field**, which
          is what makes ``company_id`` and ``routing_key`` queryable rather than
          something to grep a message for. The reserved set is what separates
          those from the machinery's own attributes. It is taken from
          :class:`logging.LogRecord`'s own documented attributes rather than
          guessed, and a new one appearing there would show up as a field
          nobody added.
        - Timestamps are UTC and ISO-8601 with an offset. A pod's clock is UTC
          and a reader's is not, and a naive timestamp is one nobody can line up
          against another service's.
        - This is deliberately not a dependency. The whole of it is the
          ``format`` method below. A library would bring a configuration surface
          to decide none of the above with.
    """

    RESERVED: ClassVar[FrozenSet[str]] = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "taskName",
            "thread",
            "threadName",
        }
    )

    CARRIED: ClassVar[Dict[str, str]] = {
        "name": "logger",
        "levelname": "level",
        "funcName": "function",
        "lineno": "line",
        "process": "pid",
    }

    def __init__(self, service_name: Optional[str] = None) -> None:
        """Initialize the formatter.

        Args:
            service_name (Optional[str]): What to label every record with. When
                omitted, no service field is written — the collector may be
                adding one from the pod's labels, and two disagreeing sources
                for it is worse than one.
        """
        super().__init__()
        self.service_name = service_name

    ############################
    # Publicly Exposed Methods #
    ############################

    def format(self, record: LogRecord) -> str:
        """Render one record as a JSON object.

        Args:
            record (LogRecord): The record to render.

        Returns:
            str: A single line of JSON, with no embedded newline.

        Notes:
            The exception goes in a field rather than after the message. A
            traceback appended to the text would be the eight-lines-of-nonsense
            case above. As a field it stays attached to the record that raised
            it and can be searched on.
        """
        payload: Dict[str, str] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),  # noqa: E501
            "message": record.getMessage(),
        }
        for attribute, name in self.CARRIED.items():
            payload[name] = getattr(record, attribute)
        if self.service_name:
            payload["service"] = self.service_name
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        for attribute, value in record.__dict__.items():
            if attribute not in self.RESERVED and not attribute.startswith("_"):  # noqa: E501
                payload[attribute] = value
        return json.dumps(payload, default=str, ensure_ascii=False)
