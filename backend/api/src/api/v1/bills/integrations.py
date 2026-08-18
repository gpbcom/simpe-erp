from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from typing import List

# Third-party imports
from fastapi import APIRouter, Depends, Path

# First-party imports
from api.dependencies import get_invoicing_service, get_manager_user
from models.auth.user import User
from models.enums import EInvoicingProvider
from models.schemas.requests.integrations.einvoicing_integration_request import (
    EInvoicingIntegrationRequest,
)
from models.schemas.responses.integrations.integration_card_response import (
    IntegrationCardResponse,
)
from service.integrations.invoicing import InvoicingService

logger: Logger = getLogger(__name__)

# Under `/billing` beside the invoicing rules, for the same reason those are:
# these are settings an agency owns, not one of its bills, and mounting them
# under `/bills/` would put them in the path space of `/bills/{bill_id}`.
router = APIRouter(prefix="/api/v1/billing", tags=["E-invoicing integrations"])


@router.get("/integrations", response_model=List[IntegrationCardResponse])
async def list_integrations(
    service: InvoicingService = Depends(get_invoicing_service),
    caller: User = Depends(get_manager_user),
) -> List[IntegrationCardResponse]:
    """Return every certified platform, with this agency's state against each.

    Args:
        service (InvoicingService): The integration service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        List[IntegrationCardResponse]: One card per supported platform.

    Notes:
        - **Every platform, configured or not.** The gallery's job is to get
          something connected, so a response listing only what already is would
          be empty on exactly the screen that matters.
        - **No response here can carry a credential.**
          :class:`~models.schemas.responses.integrations.integration_card_response.IntegrationCardResponse`
          has no field for one; what a card carries is the masked tail, which
          lets a manager recognise their own key and nobody else use it.
    """
    return await service.list_cards(caller.company_id)


@router.put("/integrations/{provider}", response_model=IntegrationCardResponse)
async def enable_integration(
    request: EInvoicingIntegrationRequest,
    provider: EInvoicingProvider = Path(description="The platform to connect."),
    service: InvoicingService = Depends(get_invoicing_service),
    caller: User = Depends(get_manager_user),
) -> IntegrationCardResponse:
    """Connect a platform, making it the one this agency transmits through.

    Args:
        request (EInvoicingIntegrationRequest): The credentials.
        provider (EInvoicingProvider): The platform to connect.
        service (InvoicingService): The integration service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        IntegrationCardResponse: The card for the now-active platform.

    Raises:
        MTIntegrationCredentialsRefused: When the platform would not accept the
            credentials. Answered as a 502 by the central handler, because the
            refusal came from a third party rather than from this payload.
        MTInvalidIntegrationCredentialsException: When a value is unusable;
            answered as a 422, with a message that never quotes the key.

    Notes:
        - **The credentials are proven against the live platform before they
          are stored.** A mistyped key is reported into the dialog that is still
          open rather than by an invoice that silently never left.
        - **Enabling one platform disables the previous one**, in the same
          transaction. An invoice has exactly one destination, and switching is
          therefore one action rather than a disable followed by an enable that
          somebody could forget.
        - The platform is in the path and not in the body, so a payload cannot
          disagree with the card a manager clicked.
    """
    actor = caller.id if caller.id else caller.email
    stored = await service.enable(
        caller.company_id, provider, request.credentials(), actor
    )
    logger.info("%s connected %s.", actor, provider.value)
    return IntegrationCardResponse.describing(
        service.catalogue.describe(provider), stored
    )


@router.delete("/integrations/{provider}", response_model=IntegrationCardResponse)
async def disable_integration(
    provider: EInvoicingProvider = Path(description="The platform to switch off."),
    service: InvoicingService = Depends(get_invoicing_service),
    caller: User = Depends(get_manager_user),
) -> IntegrationCardResponse:
    """Stop transmitting through a platform, keeping its credentials.

    Args:
        provider (EInvoicingProvider): The platform to switch off.
        service (InvoicingService): The integration service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        IntegrationCardResponse: The card for the now-inactive platform.

    Raises:
        MTIntegrationNotConfigured: When the agency never connected it;
            answered as a 404.

    Notes:
        The credentials stay. Pausing a platform for a month should not mean
        finding its API key again, and the row is also the record of what was
        once connected — useful precisely when somebody asks where last
        quarter's invoices went.
    """
    actor = caller.id if caller.id else caller.email
    stored = await service.disable(caller.company_id, provider, actor)
    logger.info("%s disconnected %s.", actor, provider.value)
    return IntegrationCardResponse.describing(
        service.catalogue.describe(provider), stored
    )


@router.post("/integrations/{provider}/check", response_model=IntegrationCardResponse)
async def check_integration(
    provider: EInvoicingProvider = Path(description="The platform to check."),
    service: InvoicingService = Depends(get_invoicing_service),
    caller: User = Depends(get_manager_user),
) -> IntegrationCardResponse:
    """Prove stored credentials again and record what happened.

    Args:
        provider (EInvoicingProvider): The platform to check.
        service (InvoicingService): The integration service.
        caller (User): The authenticated caller; enforces manager access.

    Returns:
        IntegrationCardResponse: The card, carrying the result of the check.

    Raises:
        MTIntegrationNotConfigured: When the agency never connected it;
            answered as a 404.

    Notes:
        **Answers 200 even when the platform refuses.** The check *ran*; what it
        found belongs on the card, where a manager can see that a key rotated at
        the far end needs re-entering. Answering 502 would leave the record
        still claiming the platform was healthy, which is the state this
        endpoint exists to correct.
    """
    checked = await service.verify(caller.company_id, provider)
    return IntegrationCardResponse.describing(
        service.catalogue.describe(provider), checked
    )
