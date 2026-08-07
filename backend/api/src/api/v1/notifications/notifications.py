from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

# First-party imports
from api.dependencies import (
    get_auth_service,
    get_current_user,
    get_notification_repository,
    get_notification_streams,
)
from api.sse.streams import NotificationStreams
from models.auth.user import User
from models.notifications.notification import Notification
from service.auth.auth import AuthService
from storage.repositories.notifications.notification import NotificationRepository

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("", response_model=List[Notification])
async def list_notifications(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    notifications: NotificationRepository = Depends(get_notification_repository),
    caller: User = Depends(get_current_user),
) -> List[Notification]:
    """Return the caller's own notifications, newest first.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        unread_only (bool): Restrict to notifications not yet read.
        notifications (NotificationRepository): The notification store.
        caller (User): The authenticated caller.

    Returns:
        List[Notification]: The caller's notifications.

    Notes:
        - There is no way to read anybody else's queue, and no parameter that
          names a recipient. The recipient is the credential.
        - **This is the delivery path, not a fallback for one.** The event
          stream carries no notification data — it says only that something
          changed — so every notification a reader ever sees arrives through
          here. That is what makes an unread notification survive a logout, a
          closed laptop and a dropped stream alike: the row is the truth, and
          this reads the row.
    """
    return await notifications.list_for(
        recipient_id=caller.id or "",
        page=page,
        size=size,
        unread_only=unread_only,
    )


@router.get("/unread-count")
async def count_unread_notifications(
    notifications: NotificationRepository = Depends(get_notification_repository),
    caller: User = Depends(get_current_user),
) -> dict:
    """Return how many notifications the caller has not read.

    Args:
        notifications (NotificationRepository): The notification store.
        caller (User): The authenticated caller.

    Returns:
        dict: ``{"unread": <count>}``.

    Notes:
        Served separately from the list so the badge can be refreshed without
        transferring a page of notifications to count them.
    """
    unread = await notifications.count_unread(caller.id or "")
    return {"unread": unread}


@router.post("/{notification_id}/read", response_model=Notification)
async def mark_notification_read(
    notification_id: str,
    notifications: NotificationRepository = Depends(get_notification_repository),
    caller: User = Depends(get_current_user),
) -> Notification:
    """Mark one of the caller's notifications as read.

    Args:
        notification_id (str): The notification to mark.
        notifications (NotificationRepository): The notification store.
        caller (User): The authenticated caller.

    Returns:
        Notification: The updated notification.

    Raises:
        HTTPException: 404 if it does not exist or is addressed to somebody
            else.

    Notes:
        **The same 404 either way, and deliberately.** The recipient is part of
        the repository's ``WHERE`` clause, so a notification belonging to
        another account is indistinguishable from one that was never written —
        telling the two apart would confirm the existence of other people's
        notifications to anybody willing to guess identifiers.
    """
    marked = await notifications.mark_read(notification_id, caller.id or "")
    if marked is None:
        logger.warning(
            "Account %s cannot mark notification %s: no such notification is "
            "addressed to them.",
            caller.id,
            notification_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No notification {notification_id!r} is addressed to you.",
        )
    return marked


@router.post("/read-all")
async def mark_all_notifications_read(
    notifications: NotificationRepository = Depends(get_notification_repository),
    caller: User = Depends(get_current_user),
) -> dict:
    """Clear the caller's unread queue.

    Args:
        notifications (NotificationRepository): The notification store.
        caller (User): The authenticated caller.

    Returns:
        dict: ``{"marked": <count>}``.
    """
    marked = await notifications.mark_all_read(caller.id or "")
    return {"marked": marked}


@router.get("/stream")
async def stream_notifications(
    request: Request,
    token: str = Query(...),
    auth: AuthService = Depends(get_auth_service),
    streams: NotificationStreams = Depends(get_notification_streams),
) -> StreamingResponse:
    """Stream a signal to the caller whenever they have something new to read.

    Args:
        request (Request): The incoming request, watched for disconnection.
        token (str): A short-lived stream token from
            ``POST /api/v1/auth/stream-token``.
        auth (AuthService): The authentication service.
        streams (NotificationStreams): This instance's open streams.

    Returns:
        StreamingResponse: An ``text/event-stream`` response.

    Raises:
        MTAuthInvalidToken: If the token is missing, expired, or not scoped for
            a stream; answered as a 401.

    Notes:
        - **The credential is in the query string because it has to be.**
          ``EventSource`` cannot set an ``Authorization`` header. What travels
          there is not the session token but a token that lives for a minute
          and is refused everywhere else, so a URL captured in a proxy log is
          worth nothing by the time anybody reads it.
        - This route authenticates itself rather than relying on the
          middleware, and is exempt from it — the middleware only understands
          bearer headers, and would leave ``request.state.user`` unset here.
        - The framing itself — the ready frame, the keep-alive interval, the
          headers that stop a proxy buffering the feed — lives in
          :class:`~api.sse.streams.NotificationStreams`. This route
          authenticates and hands over.
    """
    user = await auth.resolve_stream_token(token)
    return streams.response(
        request=request,
        recipient_id=user.id or "",
        user_email=str(user.email),
    )
