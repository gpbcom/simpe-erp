from __future__ import annotations

# Standard library imports
import asyncio
import json
from logging import Logger, getLogger
from typing import AsyncIterator, List

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
from models.auth.user import User
from models.notifications.notification import Notification
from service.auth.auth import AuthService
from service.notifications.notifications import NotificationService

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])

# How long the stream waits for a frame before writing a keep-alive comment.
# Proxies and load balancers close an idle connection, usually at sixty
# seconds, and a stream that is quiet all afternoon is the normal case.
KEEPALIVE_SECONDS: float = 20.0


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
    broadcaster=Depends(get_notification_broadcaster),
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
        - A keep-alive comment goes out every ``KEEPALIVE_SECONDS`` so that an
          idle stream is not closed by a proxy. A comment frame is ignored by
          ``EventSource`` and costs three bytes.
    """
    user = await auth.resolve_stream_token(token)
    recipient_id = user.id or ""
    logger.info("Opening an event stream for %s.", user.email)

    async def events() -> AsyncIterator[str]:
        """Yield SSE frames until the client goes away.

        Yields:
            str: One SSE frame, either a notification or a keep-alive comment.
        """
        queue = broadcaster.subscribe(recipient_id)
        try:
            # Announced immediately so a client knows the stream is live rather
            # than merely accepted; a browser cannot otherwise tell the two
            # apart until the first real event, which may be hours away.
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    notification = await asyncio.wait_for(
                        queue.get(), timeout=KEEPALIVE_SECONDS
                    )
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                payload = json.dumps(notification.model_dump(mode="json"))
                yield f"event: notification\ndata: {payload}\n\n"
        finally:
            broadcaster.unsubscribe(recipient_id, queue)
            logger.info("Closed the event stream for %s.", user.email)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx buffers a response by default, which would hold every frame
            # until the stream closed — turning a live feed into one long
            # silence followed by a burst.
            "X-Accel-Buffering": "no",
        },
    )
