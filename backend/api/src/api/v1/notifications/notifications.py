from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

# First-party imports
from api.dependencies import (
    get_auth_service,
    get_current_user,
    get_notification_broadcaster,
    get_notification_service,
)
from api.sse.broadcaster import NotificationBroadcaster
from api.sse.notification_stream import NotificationStream
from models.auth.user import User
from models.notifications.notification import Notification
from service.auth.auth import AuthService
from service.notifications.notifications import NotificationService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("", response_model=List[Notification])
async def list_notifications(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    unread_only: bool = Query(default=False),
    service: NotificationService = Depends(get_notification_service),
    caller: User = Depends(get_current_user),
) -> List[Notification]:
    """Return the caller's own notifications, newest first.

    Args:
        page (int): One-based page number.
        size (int): Page size.
        unread_only (bool): Restrict to notifications not yet read.
        service (NotificationService): The notification service.
        caller (User): The authenticated caller.

    Returns:
        List[Notification]: The caller's notifications.

    Notes:
        There is no way to read anybody else's queue, and no parameter that
        names a recipient. The recipient is the credential.
    """
    return await service.list_for(
        recipient_id=caller.id or "",
        page=page,
        size=size,
        unread_only=unread_only,
    )


@router.get("/unread-count")
async def count_unread_notifications(
    service: NotificationService = Depends(get_notification_service),
    caller: User = Depends(get_current_user),
) -> dict:
    """Return how many notifications the caller has not read.

    Args:
        service (NotificationService): The notification service.
        caller (User): The authenticated caller.

    Returns:
        dict: ``{"unread": <count>}``.

    Notes:
        Served separately from the list so the badge can be refreshed without
        transferring a page of notifications to count them.
    """
    unread = await service.unread_count(caller.id or "")
    return {"unread": unread}


@router.post("/{notification_id}/read", response_model=Notification)
async def mark_notification_read(
    notification_id: str,
    service: NotificationService = Depends(get_notification_service),
    caller: User = Depends(get_current_user),
) -> Notification:
    """Mark one of the caller's notifications as read.

    Args:
        notification_id (str): The notification to mark.
        service (NotificationService): The notification service.
        caller (User): The authenticated caller.

    Returns:
        Notification: The updated notification.

    Raises:
        MTNotificationNotFound: If it does not exist or is addressed to
            somebody else; answered as a 404 either way.
    """
    return await service.mark_read(notification_id, recipient_id=caller.id or "")


@router.post("/read-all")
async def mark_all_notifications_read(
    service: NotificationService = Depends(get_notification_service),
    caller: User = Depends(get_current_user),
) -> dict:
    """Clear the caller's unread queue.

    Args:
        service (NotificationService): The notification service.
        caller (User): The authenticated caller.

    Returns:
        dict: ``{"marked": <count>}``.
    """
    marked = await service.mark_all_read(caller.id or "")
    return {"marked": marked}


@router.get("/stream")
async def stream_notifications(
    request: Request,
    token: str = Query(...),
    auth: AuthService = Depends(get_auth_service),
    broadcaster: NotificationBroadcaster = Depends(get_notification_broadcaster),
) -> StreamingResponse:
    """Stream the caller's notifications as Server-Sent Events.

    Args:
        request (Request): The incoming request, watched for disconnection.
        token (str): A short-lived stream token from
            ``POST /api/v1/auth/stream-token``.
        auth (AuthService): The authentication service.
        broadcaster (NotificationBroadcaster): The in-process fan-out.

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
          :class:`~api.sse.notification_stream.NotificationStream`. This route
          authenticates and hands over.
    """
    user = await auth.resolve_stream_token(token)
    stream = NotificationStream(
        request=request,
        broadcaster=broadcaster,
        recipient_id=user.id or "",
        user_email=str(user.email),
        logger=logger,
    )
    return stream.response()
