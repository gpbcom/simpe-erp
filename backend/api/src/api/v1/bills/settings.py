from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger

# Third-party imports
from fastapi import APIRouter, Depends

# First-party imports
from api.dependencies import get_billing_service, get_manager_user
from models.auth.user import User
from models.schemas.requests.billing.billing_settings_request import (
    BillingSettingsRequest,
)
from models.settings.billing_settings import BillingSettings
from service.billing.billings import BillingService

logger: Logger = getLogger(__name__)

# The module lives under `bills/` with the two routers it belongs beside, but
# the URL keeps the `/billing` prefix, and the divergence is deliberate twice
# over. Moving it to `/api/v1/bills/settings` would collide with
# `/api/v1/bills/{bill_id}` — the same shape — so the mounting order in
# `main.py` would decide whether asking for the rules looked up a bill numbered
# "settings". And these are the agency's invoicing *rules*, not one of its
# bills, so they read better under a noun of their own.
router = APIRouter(prefix="/api/v1/billing", tags=["Billing settings"])


@router.get("/settings", response_model=BillingSettings)
async def get_billing_settings(
    service: BillingService = Depends(get_billing_service),
    _: User = Depends(get_manager_user),
) -> BillingSettings:
    """Return the agency's invoicing rules.

    Args:
        service (BillingService): The billing service.
        _ (User): The authenticated caller; enforces manager access.

    Returns:
        BillingSettings: The stored rules.

    Raises:
        MTBillingSettingsUnavailable: When the rules can neither be read nor
            seeded. Answered as a 503 by the central handler.

    Notes:
        Seeds the row from ``app.yaml`` on the first read, the way the planning
        rules do. A screen asking for them before anybody has saved any gets the
        configured defaults rather than a 404 it would have to interpret.
    """
    return await service.current_settings()


@router.put("/settings", response_model=BillingSettings)
async def update_billing_settings(
    request: BillingSettingsRequest,
    service: BillingService = Depends(get_billing_service),
    caller: User = Depends(get_manager_user),
) -> BillingSettings:
    """Replace the agency's invoicing rules.

    Args:
        request (BillingSettingsRequest): The whole rule set.
        service (BillingService): The billing service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        BillingSettings: The stored rules.

    Raises:
        MTBillingSettingsUnavailable: When the rules are not seeded. Answered
            as a 503 by the central handler.

    Notes:
        - **The whole rule set, never a partial body.** Every field on the
          request carries a default matching the stored model's, so a payload
          omitting one would silently reset it — on values printed on every
          invoice the agency sends.
        - A change applies to the **next** generation run. An invoice already
          issued keeps the terms it was printed with, because those terms are
          part of what the customer was told rather than a live lookup.
        - Manager-gated, which is the specification's own rule: the periodicity
          is a setting a manager or an administrator owns.
    """
    actor = caller.id if caller.id else caller.email
    logger.info("%s is changing the invoicing rules.", actor)
    return await service.update_settings(request, actor)
