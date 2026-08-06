from __future__ import annotations

# Standard library imports
from logging import Logger, getLogger
from secrets import compare_digest
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Header, HTTPException, status

# First-party imports
from api.dependencies import (
    get_app_config,
    get_customer_service,
    get_email_service,
    get_hca_service,
    get_planning_service,
    get_quote_service,
    get_user_repository,
)
from models.auth.user import User
from models.enums import QuoteStatus, UserRole
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.planning_completed_request import (
    PlanningCompletedRequest,  # noqa: E501
)
from models.schemas.responses.email_dispatch_response import (
    EmailDispatchResponse,  # noqa: E501
)
from service.customers.customers import CustomerService
from service.emails.emails import EmailService
from service.hcas.hcas import HcaService
from service.planning.plannings import PlanningService
from service.quotes.quotes import QuoteService
from storage.repositories.user import UserRepository

logger: Logger = getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


@router.post("/planning-completed", response_model=EmailDispatchResponse)
async def planning_completed(
    request: PlanningCompletedRequest,
    x_webhook_token: Optional[str] = Header(default=None),
    emails: EmailService = Depends(get_email_service),
    plannings: PlanningService = Depends(get_planning_service),
    hcas: HcaService = Depends(get_hca_service),
    quotes: QuoteService = Depends(get_quote_service),
    customers: CustomerService = Depends(get_customer_service),
    users: UserRepository = Depends(get_user_repository),
) -> EmailDispatchResponse:
    """Email a finished planning to its assistants and its quotes to customers.

    Args:
        request (PlanningCompletedRequest): Names the run that finished.
        x_webhook_token (Optional[str]): The shared secret, as a header.
        emails (EmailService): Sends the documents.
        plannings (PlanningService): Reads the run and the diaries.
        hcas (HcaService): Supplies the assistants' addresses.
        quotes (QuoteService): Supplies the accepted quotes of the period.
        customers (CustomerService): Supplies the customers' addresses.
        users (UserRepository): Supplies the manager and administrator
            accounts that receive the consolidated copy.

    Returns:
        EmailDispatchResponse: How many of each document went out.

    Raises:
        HTTPException: 401 when the shared secret is missing or wrong.
        MTPlanningRunNotFound: If the run does not exist; answered as a 404.

    Notes:
        - **Not** behind the bearer-token middleware: a webhook has no signed-in
          user. The shared secret is what authenticates it, compared with
          :func:`~secrets.compare_digest` so a wrong token cannot be found one
          character at a time by timing the answer.
        - The endpoint coordinates rather than decides: it reads what the run
          produced and hands it to the email service. What a document looks
          like belongs to the formatter, who receives it to the email service,
          and neither is reachable from the payload.
        - The dispatch is **weekly**: the run's period is cut on ISO week
          boundaries by the email service, so a fortnight's run sends two
          rounds of documents rather than one nobody can read.
        - Delivery failures do not fail the call. A bounced mailbox is not a
          reason to tell the caller its planning run went wrong — the counts in
          the answer say what actually left.
    """
    configured = get_app_config().webhook.get_token()
    if not configured or not x_webhook_token:
        logger.warning("Refused a planning-completed webhook with no secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This webhook requires a shared secret.",
        )
    if not compare_digest(x_webhook_token, configured):
        logger.warning("Refused a planning-completed webhook with a wrong secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This webhook requires a shared secret.",
        )

    run = await plannings.get_run(request.run_id)
    logger.info(
        "Dispatching the documents of planning run %s (%s to %s).",
        run.id,
        run.period_start,
        run.period_end,
    )
    # The caller is synthesised because a webhook has no signed-in user, but it
    # is no longer synthesised out of nothing: every account belongs to an
    # agency, so this one takes the agency of whoever asked for the run. It used
    # to carry no company at all, which was the one state that let an account
    # act across every agency at once — exactly what the mandatory company
    # exists to remove.
    requester = await users.get(run.requested_by)
    if requester is None:
        logger.error(
            "Planning run %s names requester %s, who no longer exists; the "
            "documents cannot be attributed to an agency.",
            run.id,
            run.requested_by,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The account that requested this run no longer exists.",
        )
    system_caller = User(
        id=run.id,
        email="planning-webhook@simple-erp.system",
        full_name="Planning webhook",
        role=UserRole.ADMIN,
        company_id=requester.company_id,
    )
    diaries = await plannings.all_plannings(
        system_caller, run.period_start, run.period_end
    )
    assistants = await hcas.list(page=1, size=500)
    managers = await users.list(page=1, size=500, role=UserRole.MANAGER)
    managers += await users.list(page=1, size=500, role=UserRole.ADMIN)
    plannings_sent = await emails.send_plannings(diaries, assistants, managers)

    accepted: List[Quote] = await quotes.list(
        page=1, size=500, status=QuoteStatus.ACCEPTED
    )
    recipients: List[Customer] = await customers.list(page=1, size=500)
    quotes_sent = await emails.send_quotes(accepted, recipients)

    logger.info(
        "Planning run %s dispatched: %d planning(s), %d quote(s).",
        run.id,
        plannings_sent,
        quotes_sent,
    )
    return EmailDispatchResponse(
        run_id=run.id,
        plannings_sent=plannings_sent,
        quotes_sent=quotes_sent,
    )
