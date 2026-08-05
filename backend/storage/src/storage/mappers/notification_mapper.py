from __future__ import annotations

# Standard library imports
from logging import Logger
from typing import Optional

# First-party imports
from models.enums import NotificationKind
from models.notifications.notification import Notification
from storage.mappers.base_mapper import BaseMapper
from storage.orm.notification_row import NotificationRow


class NotificationMapper(BaseMapper[Notification, NotificationRow]):
    """Converts between :class:`Notification` and its row.

    Notes:
        The kind is round-tripped through
        :class:`~models.enums.NotificationKind` on the way down rather than
        written straight off the model, so the column can only hold a value a
        client knows how to render. A kind nothing recognises is a row that
        appears in the list as an unlabelled blank.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            logger (Optional[Logger]): Logger to use. Defaults to a logger
                named after the base mapper's module.
        """
        super().__init__(
            model_class=Notification,
            row_class=NotificationRow,
            logger=logger,
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _build_model(self, row: NotificationRow) -> Notification:
        """Build a notification from a row's columns.

        Args:
            row (NotificationRow): The row to read.

        Returns:
            Notification: The domain model.

        Raises:
            MTInvalidNotificationException: If a stored value no longer
                satisfies the model's validators.
        """
        self.logger.debug(
            "Building a notification from row %s (kind %s, read %s).",
            row.id,
            row.kind,
            row.is_read,
        )
        return Notification(
            id=row.id,
            recipient_id=row.recipient_id,
            kind=row.kind,
            title=row.title,
            body=row.body,
            quote_id=row.quote_id,
            is_read=row.is_read,
            created_at=self.timestamps.to_utc(row.created_at),
            read_at=self.timestamps.to_utc(row.read_at),
        )

    def _apply_fields(self, row: NotificationRow, model: Notification) -> None:
        """Write a notification's fields onto a row.

        Args:
            row (NotificationRow): The row to write to.
            model (Notification): The model carrying the values.
        """
        kind = NotificationKind(model.kind)
        self.logger.debug(
            "Applying a notification onto row %s (kind %s, recipient %s).",
            row.id,
            kind.value,
            model.recipient_id,
        )
        row.recipient_id = model.recipient_id
        row.kind = kind.value
        row.title = model.title
        row.body = model.body
        row.quote_id = model.quote_id
        row.is_read = model.is_read
        row.read_at = model.read_at
        if kind.concerns_a_quote() and model.quote_id is None:
            self.logger.warning(
                "Notification row %s is about a quote but names none; the "
                "reader will have nowhere to click through to.",
                row.id,
            )
