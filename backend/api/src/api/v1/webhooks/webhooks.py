from __future__ import annotations

# Standard library imports
from datetime import UTC, datetime
from logging import Logger, getLogger
from secrets import compare_digest
from typing import List, Optional

# Third-party imports
from fastapi import APIRouter, Depends, Header, HTTPException, status

# First-party imports
from api.dependencies import (
    get_invoicing_service,
    get_billing_service,
    get_app_config,
    get_customer_service,
    get_email_service,
    get_hca_service,
    get_planning_service,
    get_quote_service,
    get_company_repository,
    get_user_repository,
)
from models.auth.user import User
from models.enums import BillStatus, QuoteStatus, UserRole
from models.people.customer import Customer
from models.quoting.quote import Quote
from models.schemas.requests.billing.bill_paid_request import BillPaidRequest
from models.schemas.requests.billing.bill_accepted_request import (
    BillAcceptedRequest,
)
from models.schemas.requests.planning.planning_completed_request import (
    PlanningCompletedRequest,  # noqa: E501
)
from models.schemas.responses.billing.bill_dispatch_response import (
    BillDispatchResponse,
)
from models.schemas.responses.messaging.email_dispatch_response import (
    EmailDispatchResponse,  # noqa: E501
)
from service.billing.billings import BillingService
from service.integrations.invoicing import InvoicingService
from service.customers.customers import CustomerService
from service.emails.emails import EmailService
from service.emails.exceptions import MTInvalidEmailException
from service.hcas.hcas import HcaService
from service.planning.plannings import PlanningService
from service.quotes.quotes import QuoteService
from storage.repositories.auth.user import UserRepository
from storage.repositories.companies.company import CompanyRepository

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
    companies: CompanyRepository = Depends(get_company_repository),
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
        companies (CompanyRepository): Resolves the agency named on every
            quote, from the account that requested the run.
        users (UserRepository): Supplies the manager and administrator
            accounts that receive the consolidated copy.

    Returns:
        EmailDispatchResponse: How many of each document went out.

    Raises:
        HTTPException: 401 when the shared secret is missing or wrong.
        MTPlanningRunNotFound: If the run does not exist. Answered as a 404.

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
            "Planning run %s names requester %s, who no longer exists. The "
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
    # The agency named on every quote, and the language it is written in,
    # both come from the account that asked for the run. Neither a customer
    # nor a quote carries a company, and there is no request here to read an
    # Accept-Language header from — which is exactly why the preference is
    # stored on the account rather than left in the browser.
    issuer = await companies.get(requester.company_id)
    if issuer is None:
        logger.error(
            "Planning run %s belongs to agency %s, which no longer exists; "
            "its quotes have no issuer to name.",
            run.id,
            requester.company_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The agency that requested this run no longer exists.",
        )
    quotes_sent = await emails.send_quotes(
        accepted, recipients, issuer, requester.language
    )

    logger.info(
        "Planning run %s dispatched: %d planning(s), %d quote(s) in %s, issued by %s.",
        run.id,
        plannings_sent,
        quotes_sent,
        requester.language.value,
        issuer.name,
    )
    return EmailDispatchResponse(
        run_id=run.id,
        plannings_sent=plannings_sent,
        quotes_sent=quotes_sent,
    )


@router.post("/bill-accepted", response_model=BillDispatchResponse)
async def bill_accepted(
    request: BillAcceptedRequest,
    x_webhook_token: Optional[str] = Header(default=None),
    emails: EmailService = Depends(get_email_service),
    billing: BillingService = Depends(get_billing_service),
    customers: CustomerService = Depends(get_customer_service),
    companies: CompanyRepository = Depends(get_company_repository),
) -> BillDispatchResponse:
    """Email a validated invoice to the customer it is addressed to.

    Args:
        request (BillAcceptedRequest): Names the invoice a manager approved.
        x_webhook_token (Optional[str]): The shared secret, as a header.
        emails (EmailService): Sends the document.
        billing (BillingService): Reads the invoice and its stored PDF.
        customers (CustomerService): Supplies the customer's address.
        companies (CompanyRepository): Names the agency on the covering note.

    Returns:
        BillDispatchResponse: Whether the customer received it.

    Raises:
        HTTPException: 401 when the shared secret is missing or wrong.
        MTBillNotFound: If the invoice does not exist. Answered as a 404.
        MTBillDocumentUnavailable: If the stored PDF cannot be read. Answered
            as a 503.

    Notes:
        - **This is what puts an invoice in a customer's inbox**, and it fires
          only after a manager moved the bill to accepted. A generation run
          renders every document and stops. Nothing reaches anybody until the
          record says a human approved it.
        - **Not** behind the bearer-token middleware: a webhook has no signed-in
          user. Its own secret is what authenticates it, compared with
          :func:`~secrets.compare_digest` so a wrong token cannot be found one
          character at a time by timing the answer. Both refusals answer with
          the same text, so a caller cannot tell an unset secret from a wrong
          one.
        - **The bytes emailed are the bytes stored**, read back from the object
          store rather than re-rendered. What the customer receives and what the
          agency can re-download are then provably the same file.
        - A delivery failure is reported, not raised. The invoice is written,
          numbered and downloadable. The bill simply stays at accepted, which
          reads as "approved but not yet out" — the truth, and actionable.
    """
    configured = get_app_config().billing_webhook.get_token()
    if not configured or not x_webhook_token:
        logger.warning("Refused a bill-accepted webhook with no secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This webhook requires a shared secret.",
        )
    if not compare_digest(x_webhook_token, configured):
        logger.warning("Refused a bill-accepted webhook with a wrong secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This webhook requires a shared secret.",
        )

    bill = await billing.get(request.bill_id)
    payload, _ = await billing.document(bill.id or request.bill_id)
    customer = await customers.get(bill.customer_id)
    company = await companies.get(bill.company_id)
    if company is None:
        logger.error(
            "Invoice %s names agency %s, which no longer exists. It cannot be "
            "sent because the covering note has nobody to come from.",
            bill.number,
            bill.company_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The agency that issued this invoice no longer exists.",
        )
    logger.info("Dispatching invoice %s to customer %s.", bill.number, bill.customer_id)
    try:
        await emails.send_bill(bill, customer, company, payload)
    except MTInvalidEmailException as exc:
        logger.error(
            "Could not email invoice %s to customer %s: %s. It stays approved "
            "and un-sent.",
            bill.number,
            bill.customer_id,
            exc,
        )
        return BillDispatchResponse(bill_id=request.bill_id, sent=False)

    sent_at = datetime.now(UTC)
    await billing.mark_sent(bill.id or request.bill_id, sent_at)
    if bill.status.can_move_to(BillStatus.WAITING_PAYMENT):
        await billing.set_status(
            bill.id or request.bill_id,
            BillStatus.WAITING_PAYMENT,
            actor="bill-webhook@simple-erp.system",
        )
    logger.info("Invoice %s reached customer %s.", bill.number, bill.customer_id)
    return BillDispatchResponse(bill_id=request.bill_id, sent=True)


@router.post("/bill-paid", response_model=BillDispatchResponse)
async def bill_paid(
    request: BillPaidRequest,
    x_webhook_token: Optional[str] = Header(default=None),
    billing: BillingService = Depends(get_billing_service),
    transmissions: InvoicingService = Depends(get_invoicing_service),
) -> BillDispatchResponse:
    """Transmit a settled invoice to the agency's certified platform.

    Args:
        request (BillPaidRequest): Names the invoice that was collected.
        x_webhook_token (Optional[str]): The shared secret, as a header.
        billing (BillingService): Reads the invoice and its stored document.
        transmissions (InvoicingService): Sends it where it must go.

    Returns:
        BillDispatchResponse: Whether the platform accepted it.

    Raises:
        HTTPException: 401 when the shared secret is missing or wrong.
        MTBillNotFound: If the invoice does not exist. Answered as a 404.

    Notes:
        - **What is transmitted depends on who owed the money**, not on this
          endpoint. A household's settled invoice is *declared* — flux 10.4,
          because VAT on services falls due on collection — and reaches nobody;
          a business receives the structured document. A public body is reached
          through Chorus Pro. Most of this agency's revenue takes the first
          route, which is why a literal reading of "send the paid bill" would be
          wrong for nearly every invoice it issues.
        - **A failed transmission answers 200 with ``sent=false``.** The payment
          is recorded and true whatever a platform said. Answering 5xx would have
          the announcement redelivered and, worse, would make a working payment
          look like a broken one. The failure is logged with the platform's own
          words.
        - **An agency with nothing connected is a 409 and stays one.** That is
          not a transmission that failed but one that could not be attempted,
          and the fix is a person connecting a platform rather than a retry.
    """
    configured = get_app_config().billing_webhook.get_token()
    if not configured or not x_webhook_token:
        logger.warning("Refused a bill-paid webhook with no secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This webhook requires a shared secret.",
        )
    if not compare_digest(x_webhook_token, configured):
        logger.warning("Refused a bill-paid webhook with a wrong secret.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This webhook requires a shared secret.",
        )

    bill = await billing.get(request.bill_id)
    document, _ = await billing.document(bill.id or request.bill_id)
    receipt = await transmissions.transmit(bill, document)
    if not receipt.succeeded():
        logger.error(
            "Invoice %s was not transmitted as %s: %s",
            bill.number,
            receipt.kind.value,
            receipt.error,
        )
        return BillDispatchResponse(bill_id=request.bill_id, sent=False)
    logger.info(
        "Invoice %s transmitted as %s (%s).",
        bill.number,
        receipt.kind.value,
        receipt.reference,
    )
    return BillDispatchResponse(bill_id=request.bill_id, sent=True)
