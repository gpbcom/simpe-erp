*** Settings ***
Documentation    Invoicing what the agency delivered, and tracking it to payment.
...
...              The application could quote work, plan it and email the quote,
...              but it could not invoice any of it. These tests walk the whole
...              of what was added: a manager sets a periodicity, asks a past
...              period to be billed, reviews what came out, validates one
...              invoice — and only then does a customer receive anything.
...
...              **The order matters more than any single assertion.** A
...              generation run renders every document and stops; nothing
...              reaches a customer until a human approves it. So the suite
...              checks Mailpit *before* validating as well as after: an empty
...              mailbox at that point is the requirement, not an absence of
...              evidence.
...
...              **Idempotent by construction.** The invoicing rules are a
...              seeded singleton that cannot be created, so they are
...              snapshotted before anything runs and written back in a teardown
...              that fires even when the test that changed them failed. The
...              invoices themselves are deliberately *not* cleaned up: a number
...              withdrawn from the series is the gap French invoicing forbids,
...              and the tests are written to tolerate a period that has already
...              been billed by an earlier run.

Library          Browser
Library          Collections
Library          DateTime
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Snapshot The Invoicing Rules And Open
Suite Teardown   Restore The Invoicing Rules And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${ORIGINAL_BILLING}    ${EMPTY}
@{QA_HOUSEHOLDS}       @{EMPTY}
@{LAST_RUN_BILLS}      @{EMPTY}
# Longer than ${EVENT_TIMEOUT}, and not arbitrarily: a quote status change is
# one broker hop, while a billing run renders a PDF and uploads an object per
# customer. The queue takes one run at a time, so several tests asking for one
# in succession genuinely serialise — which is the shape the third worker role
# exists for, not something to wait twenty seconds on and call flaky.
${BILLING_TIMEOUT}     120s


*** Test Cases ***
The Invoices Are Reachable From The Navigation
    [Documentation]    A screen with no door into it is a screen nobody finds.
    ...
    ...    Walked rather than typed. ``nav.planningSettings`` once existed in
    ...    both bundles with no route behind it, and the catch-all redirected
    ...    home — which looks exactly like a permission problem.
    [Tags]    smoke    navigation    billing
    Sign In As    ${MANAGER_EMAIL}
    Wait For Elements State    [data-testid="nav--bills"]    visible
    ...    message=The invoices have no navigation entry.
    Click    [data-testid="nav--bills"]
    Wait For Elements State    [data-testid="bills-page"]    visible
    ...    message=The bills page did not open; the route may be missing.
    [Teardown]    Sign Out

The Billing Rules Are Reachable And Say They Re-Issue Nothing
    [Documentation]    **The expectation that would otherwise be discovered.**
    ...
    ...    Changing the payment terms does not correct an invoice already sent:
    ...    the terms printed on it are part of what the customer was told. A
    ...    manager who assumed otherwise would be waiting for corrected
    ...    documents that are never coming.
    [Tags]    smoke    navigation    billing-settings
    Sign In As    ${MANAGER_EMAIL}
    Wait For Elements State    [data-testid="nav--billing-settings"]    visible
    ...    message=The billing rules have no navigation entry.
    Click    [data-testid="nav--billing-settings"]
    Wait For Elements State    [data-testid="billing-settings-page"]    visible
    Wait For Elements State    [data-testid="billing-settings-notice"]    visible
    ...    message=The screen does not say that a change re-issues nothing.
    [Teardown]    Sign Out

A Manager Changes The Periodicity And The Server Keeps It
    [Documentation]    Requirement 2 and 4, asserted against the *server*.
    ...
    ...    The periodicity is a stored rule a manager owns, not a deployment
    ...    value. Read back over the API rather than off the field, because a
    ...    form that accepts a keystroke and never saves it looks identical.
    [Tags]    billing-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Billing Rules
    Select Options By    [data-testid="billing-periodicity"]    value    weekly
    Fill Text    [data-testid="billing-payment-terms"]    45
    Click    [data-testid="billing-settings-save"]
    Wait For Elements State    [data-testid="billing-settings-saved"]    visible
    ...    message=The billing rules were not saved.

    ${stored}=    Invoicing Rules As Stored
    Should Be Equal    ${stored}[periodicity]    weekly
    Should Be Equal As Integers    ${stored}[payment_terms_days]    45
    [Teardown]    Restore The Invoicing Rules And Sign Out

Payment Terms Beyond The Statutory Ceiling Cannot Be Saved
    [Documentation]    The ceiling is law, not a preference.
    ...
    ...    The code de commerce caps agreed payment terms, so a longer one would
    ...    print an obligation the agency could not enforce. Refused on the
    ...    screen *and* by the server; this walks the screen's half.
    [Tags]    billing-settings
    Sign In As    ${MANAGER_EMAIL}
    Open The Billing Rules
    Fill Text    [data-testid="billing-payment-terms"]    90
    Wait For Elements State    [data-testid="billing-settings-problem"]    visible
    ...    message=A 90-day payment term was accepted; the statutory ceiling is 60.
    Get Element States    [data-testid="billing-settings-save"]    contains    disabled
    [Teardown]    Reload And Sign Out

Generating A Period Writes Invoices That Nobody Has Been Sent
    [Documentation]    **Requirement 6, and the order it actually happens in.**
    ...
    ...    A generation run renders every document and stops. The mail catcher
    ...    is emptied first and checked after, so an empty mailbox here is the
    ...    assertion rather than the absence of one: nothing may reach a
    ...    customer until a manager approves it.
    [Tags]    billing    generation
    Ensure There Is Work To Bill
    Clear The Mail Catcher
    Bill A Past Period Through The API
    ${messages}=    Mail Catcher Message Count
    Should Be Equal As Integers    ${messages}    0
    ...    msg=Generating invoices emailed ${messages} customer(s); nothing may be sent before validation.

Every Invoice A Run Writes Is Waiting To Be Validated
    [Documentation]    The status a generated invoice starts in.
    ...
    ...    Read over the API rather than off the grid, so the assertion is about
    ...    the record and not about a chip's colour.
    [Tags]    billing    generation
    Ensure There Is Work To Bill
    Bill A Past Period Through The API
    Skip If    not $LAST_RUN_BILLS
    ...    The period was billed by an earlier run, so this one wrote nothing.
    FOR    ${bill_id}    IN    @{LAST_RUN_BILLS}
        ${bill}=    Invoice As Stored    ${bill_id}
        Should Be Equal    ${bill}[status]    to-be-validated
        ...    msg=Invoice ${bill}[number] was written as ${bill}[status]; a run must leave every invoice awaiting validation.
        Should Be Equal    ${bill}[sent_at]    ${None}
        ...    msg=Invoice ${bill}[number] reports itself as sent; a run sends nothing.
    END

An Invoice Charges Only The Work Inside Its Window
    [Documentation]    **Requirement 3, made testable.**
    ...
    ...    A quote line carries one service date, so "only the part inside the
    ...    window is billed" is a date filter and no fractional amount is
    ...    computed anywhere. Every charge on an invoice must therefore fall
    ...    inside the period it names — a property the model enforces and this
    ...    confirms end to end.
    [Tags]    billing    pro-rata
    Ensure There Is Work To Bill
    Bill A Past Period Through The API
    ${bills}=    Invoices As Stored
    Should Not Be Empty    ${bills}
    FOR    ${bill}    IN    @{bills}
        ${outside}=    Evaluate
        ...    [l["service_date"] for l in $bill["lines"] if not ($bill["period_start"] <= l["service_date"] <= $bill["period_end"])]
        Should Be Empty    ${outside}
        ...    msg=Invoice ${bill}[number] covers ${bill}[period_start]..${bill}[period_end] but charges for @{outside}.
    END

Generating The Same Period Twice Produces No Second Invoice
    [Documentation]    **The duplicate-billing guard, end to end.**
    ...
    ...    Two runs waking together both pass the service's own check; the
    ...    unique index is what stops the customer receiving two invoices for
    ...    one month. A re-run is a reported no-op, and the count must not move.
    [Tags]    billing    idempotency
    Ensure There Is Work To Bill
    Bill A Past Period Through The API
    ${before}=    Invoice Count As Stored
    Bill A Past Period Through The API
    ${after}=    Invoice Count As Stored
    Should Be Equal As Integers    ${before}    ${after}
    ...    msg=Billing the same period twice went from ${before} to ${after} invoice(s).

An Invoice Names No Quote Anywhere On The Screen
    [Documentation]    **Requirement 9, made testable.**
    ...
    ...    A bill lists interventions, never quotes. The originating line is
    ...    stored so a disputed charge can be traced in a support conversation,
    ...    but a manager reading it off the screen and quoting it to a customer
    ...    would be reading from a document the customer does not hold.
    [Tags]    billing    requirement-9
    Ensure There Is Work To Bill
    Bill A Past Period Through The API
    Sign In As    ${MANAGER_EMAIL}
    Open The First Invoice
    ${text}=    Get Text    [data-testid="bill-detail-drawer"]
    ${lowered}=    Convert To Lower Case    ${text}
    Should Not Contain    ${lowered}    quote
    ...    msg=The invoice drawer names a quote; a bill must list only interventions.
    Should Not Contain    ${lowered}    devis
    ...    msg=The invoice drawer names a quote; a bill must list only interventions.
    [Teardown]    Sign Out

The Invoice Downloads As A PDF Behind The Credential
    [Documentation]    **Requirement 5, and the guard around it.**
    ...
    ...    The documents live under a private prefix precisely so this endpoint
    ...    is the only way to them. Fetched with the credential it is a PDF;
    ...    fetched without one it is refused, which is what makes storing them
    ...    privately worth doing.
    [Tags]    billing    document
    Ensure There Is Work To Bill
    Bill A Past Period Through The API
    ${bills}=    Invoices As Stored
    Should Not Be Empty    ${bills}
    ${bill_id}=    Set Variable    ${bills}[0][id]

    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${document}=    GET
    ...    ${API_URL}/api/v1/bills/${bill_id}/document
    ...    headers=${headers}
    ...    expected_status=200
    Should Contain    ${document.headers}[Content-Type]    application/pdf
    Should Contain    ${document.headers}[Content-Disposition]    attachment
    Should Start With    ${document.content}    ${{ b"%PDF-" }}
    ...    msg=The download did not return a PDF.

    ${anonymous}=    GET
    ...    ${API_URL}/api/v1/bills/${bill_id}/document
    ...    expected_status=any
    Should Be Equal As Integers    ${anonymous.status_code}    401
    ...    msg=An invoice was downloadable without a credential.

Validating An Invoice Is What Sends It To The Customer
    [Documentation]    **The step requirement 6 actually attaches to.**
    ...
    ...    The mail catcher is emptied, one invoice is approved, and the message
    ...    is waited on: the dispatch goes through a broker and a webhook, so
    ...    asserting immediately would fail on a slow machine and pass on a fast
    ...    one. The invoice then advances to awaiting payment on its own.
    [Tags]    billing    delivery
    Ensure There Is Work To Bill
    Bill A Past Period Through The API
    ${bill}=    An Invoice Waiting To Be Validated
    Skip If    $bill is None
    ...    Every invoice has already been validated by an earlier run.
    Clear The Mail Catcher

    Move Invoice To    ${bill}[id]    accepted
    Wait Until Keyword Succeeds    ${BILLING_TIMEOUT}    2s
    ...    The Mail Catcher Should Hold At Least    1
    Wait Until Keyword Succeeds    ${BILLING_TIMEOUT}    2s
    ...    Invoice Status Should Be    ${bill}[id]    waiting-payment

An Invoice Cannot Skip A Step In Its Lifecycle
    [Documentation]    The audit trail the four statuses exist to keep.
    ...
    ...    A bill going straight from awaiting validation to paid would skip the
    ...    record of it ever having been approved, and of it ever having been
    ...    sent. Refused with a conflict rather than a malformed-payload error:
    ...    the request is well formed and the invoice is simply not in the state
    ...    the act applies to.
    [Tags]    billing    lifecycle
    Ensure There Is Work To Bill
    Bill A Past Period Through The API
    ${bill}=    An Invoice Waiting To Be Validated
    Skip If    $bill is None
    ...    Every invoice has already been validated by an earlier run.

    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    status=paid
    ${refused}=    PATCH
    ...    ${API_URL}/api/v1/bills/${bill}[id]/status
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${refused.status_code}    409
    ...    msg=An invoice was moved straight to paid, skipping validation and delivery.

A Customer Billed Weekly Gets Their Own Window
    [Documentation]    **The agency rule is a default, not a ceiling.**
    ...
    ...    A household paying week by week and an institution wanting one
    ...    document a year are both ordinary, and a single agency-wide setting
    ...    serves neither. The agency is put on monthly and this customer on
    ...    weekly, so the seven-day window on the invoice can only have come
    ...    from the customer's own rule.
    ...
    ...    Registered fresh rather than borrowed from the book: the customers
    ...    the earlier tests billed are covered by a monthly invoice, and a
    ...    window inside one already issued is refused — which is the guard
    ...    against charging somebody twice for days they have paid for.
    [Tags]    billing    per-customer
    Set The Agency Periodicity To    monthly
    ${customer_id}=    Register A Household Billed    weekly
    Give Work Inside The Billed Period To    ${customer_id}
    Bill A Past Period Through The API

    ${bill}=    The Invoice Of    ${customer_id}
    Should Be Equal    ${bill}[periodicity]    weekly
    ...    msg=Invoice ${bill}[number] was issued monthly; the customer is billed weekly.
    ${days}=    Evaluate
    ...    (datetime.date.fromisoformat($bill["period_end"]) - datetime.date.fromisoformat($bill["period_start"])).days
    ...    modules=datetime
    Should Be Equal As Integers    ${days}    6
    ...    msg=The invoice covers ${bill}[period_start]..${bill}[period_end], which is not one week.
    [Teardown]    Restore The Invoicing Rules

A Customer With No Rule Of Their Own Follows The Agency
    [Documentation]    The ordinary case, and the one that must not drift.
    ...
    ...    Unset has to keep meaning "whatever the agency bills on". Were it
    ...    frozen to a copy of today's setting, every household would look
    ...    unchanged now and stop following the rule the moment a manager moved
    ...    it — with nothing on any screen saying why.
    [Tags]    billing    per-customer
    Set The Agency Periodicity To    yearly
    ${customer_id}=    Register A Household Billed    ${None}
    ${stored}=    Customer Billing Periodicity Of    ${customer_id}
    Should Be Equal    ${stored}    ${None}
    ...    msg=A newly registered household was given a periodicity of its own.
    [Teardown]    Restore The Invoicing Rules

A Manager Sets And Clears The Granularity From The Customer's File
    [Documentation]    **Requirement 4, on the screen the decision is taken.**
    ...
    ...    Read back over the API rather than off the control, because a select
    ...    that accepts a choice and never sends it looks identical. Clearing is
    ...    walked as well as setting: an override that cannot be taken off is
    ...    one a household keeps for good.
    [Tags]    billing    per-customer
    ${customer_id}=    Register A Household Billed    ${None}
    Sign In As    ${MANAGER_EMAIL}
    Open The File Of Customer    ${customer_id}

    Select Options By    [data-testid="customer-billing-periodicity"]    value    yearly
    Wait For Elements State    [data-testid="customer-billing-saved"]    visible
    ...    message=The periodicity was not saved.
    ${stored}=    Customer Billing Periodicity Of    ${customer_id}
    Should Be Equal    ${stored}    yearly

    Select Options By    [data-testid="customer-billing-periodicity"]    value    ${EMPTY}
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    1s
    ...    Customer Should Follow The Agency    ${customer_id}
    [Teardown]    Sign Out

An Assistant May Not Change How Often A Customer Is Billed
    [Documentation]    Requirement 4's other half: who may not.
    ...
    ...    How often a household is asked for money is a commercial decision.
    ...    Asserted over the API, because a control an assistant never sees is a
    ...    convenience and the guard is what actually refuses.
    [Tags]    billing    per-customer    security
    ${customer_id}=    Register A Household Billed    ${None}
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    periodicity=weekly
    ${refused}=    PATCH
    ...    ${API_URL}/api/v1/customers/${customer_id}/billing-periodicity
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${refused.status_code}    403
    ...    msg=An assistant changed how often a customer is invoiced.

An Assistant May Not Read The Agency's Invoices
    [Documentation]    Money is not an assistant's to see.
    ...
    ...    Asserted over the API rather than by looking for a missing menu
    ...    entry: a hidden navigation item is a convenience, and the guard is
    ...    what actually refuses.
    [Tags]    billing    security
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${refused}=    GET
    ...    ${API_URL}/api/v1/bills
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${refused.status_code}    403
    ...    msg=An assistant could read the agency's invoices.


*** Keywords ***
Snapshot The Invoicing Rules And Open
    [Documentation]    Record the rules as found, then open the browser.
    ...
    ...    The rules are a seeded singleton with no create and no delete, so the
    ...    only way this suite stays runnable twice is to put back exactly what
    ...    it found.
    ${rules}=    Invoicing Rules As Stored
    Set Suite Variable    ${ORIGINAL_BILLING}    ${rules}
    Open The Application

Restore The Invoicing Rules And Close
    [Documentation]    Put the rules back, drop the fixtures, close the browser.
    Run Keyword And Ignore Error    Restore The Invoicing Rules
    Run Keyword And Ignore Error    Remove The Households This Run Registered
    Close The Application

Remove The Households This Run Registered
    [Documentation]    Delete the fixture customers, and only those.
    ...
    ...    ``expected_status=any`` because the one that was invoiced is refused:
    ...    a customer named on an accounting record cannot be deleted, which is
    ...    the right rule. That household stays, as its invoice does — a number
    ...    withdrawn from the series is the gap French invoicing forbids.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    FOR    ${customer_id}    IN    @{QA_HOUSEHOLDS}
        DELETE
        ...    ${API_URL}/api/v1/customers/${customer_id}
        ...    headers=${headers}
        ...    expected_status=any
    END

Restore The Invoicing Rules And Sign Out
    [Documentation]    Undo a test that changed the rules, then end the session.
    Run Keyword And Ignore Error    Restore The Invoicing Rules
    Sign Out

Restore The Invoicing Rules
    [Documentation]    Write back the rules this suite found.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    periodicity=${ORIGINAL_BILLING}[periodicity]
    ...    payment_terms_days=${ORIGINAL_BILLING}[payment_terms_days]
    ...    late_penalty_multiplier=${ORIGINAL_BILLING}[late_penalty_multiplier]
    ...    recovery_indemnity_eur=${ORIGINAL_BILLING}[recovery_indemnity_eur]
    ...    escompte_offered=${ORIGINAL_BILLING}[escompte_offered]
    PUT
    ...    ${API_URL}/api/v1/billing/settings
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Invoicing Rules As Stored
    [Documentation]    Return the invoicing rules the server holds.
    ...
    ...    Seeded by the server on first read, so this never has to handle a
    ...    404 the way a screen would.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/billing/settings
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Open The Billing Rules
    [Documentation]    Follow the navigation entry and wait for the form.
    ...
    ...    Waits for a field rather than for the page, because the form is
    ...    populated from the query and a test that filled it before the
    ...    response landed would type into a control that is about to be reset.
    Click    [data-testid="nav--billing-settings"]
    Wait For Elements State    [data-testid="billing-payment-terms"]    visible
    ...    message=The billing rules form never populated.

Open The First Invoice
    [Documentation]    Open the bills page and click into the first row.
    Click    [data-testid="nav--bills"]
    Wait For Elements State    [data-testid="bills-grid"]    visible
    # ``>> nth=0`` is not decoration: Playwright runs strict, so a bare
    # ``.MuiDataGrid-row`` matching two rows is an error rather than a match,
    # and the failure reads as an empty grid when the grid is in fact full.
    Wait For Elements State    .MuiDataGrid-row >> nth=0    visible
    ...    message=The bills grid is empty; was a period billed first?
    Click    .MuiDataGrid-row >> nth=0
    Wait For Elements State    [data-testid="bill-detail-drawer"]    visible
    ...    message=The invoice drawer did not open.

The Day Being Billed
    [Documentation]    Return a day comfortably inside a finished period.
    ...
    ...    Forty-five days back, so the window it falls in has ended whatever
    ...    the configured periodicity is — the service refuses a period that has
    ...    not finished, because care that has not happened cannot be invoiced.
    ${day}=    Get Current Date    increment=-45 days    result_format=%Y-%m-%d
    RETURN    ${day}

Ensure There Is Work To Bill
    [Documentation]    Give the billed period something to invoice.
    ...
    ...    **The seeder plans its work into the future**, so no finished period
    ...    holds anything billable on a fresh stack. Without this the suite
    ...    would pass only where somebody had happened to leave a past quote
    ...    behind — which is the same class of accident
    ...    ``Ensure A Planning Has Been Computed`` exists to remove.
    ...
    ...    Skipped when the period already carries an invoice: the guard makes a
    ...    second run a no-op, and adding more accepted work to a billed period
    ...    would only produce lines nothing will ever charge for.
    ${bills}=    Invoices As Stored
    ${day}=    The Day Being Billed
    ${already}=    Evaluate
    ...    [b for b in $bills if b["period_start"] <= "${day}" <= b["period_end"]]
    IF    ${already}
        Log    ${day} is already billed by ${already}[0][number].    console=${True}
        RETURN
    END
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${customer_id}=    First Customer Of    ${ASSISTANT_EMAIL}
    ${type_id}=    First Intervention Type
    ${suffix}=    Unique Suffix
    ${body}=    Catenate    SEPARATOR=
    ...    {"reference": "QA-BILL-${suffix}",
    ...    "customer_id": "${customer_id}",
    ...    "lines": [{"name": "Aide a la toilette",
    ...    "intervention_type_id": "${type_id}",
    ...    "service_category": "necessity",
    ...    "service_date": "${day}",
    ...    "earliest_start": "09:00:00",
    ...    "latest_end": "12:00:00",
    ...    "duration_minutes": 120}]}
    ${quote}=    POST
    ...    ${API_URL}/api/v1/quotes
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=201
    # A draft is accepted outright; `validate` is for the queue a submitted
    # quote sits in, and answers 409 for anything else.
    POST
    ...    ${API_URL}/api/v1/quotes/${quote.json()}[id]/accept
    ...    headers=${headers}
    ...    expected_status=200
    Log    Created and accepted a quote covering ${day}.    console=${True}

Invoice As Stored
    [Documentation]    Return one invoice.
    [Arguments]    ${bill_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/bills/${bill_id}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Bill A Past Period Through The API
    [Documentation]    Ask for a finished period to be billed, and wait for it.
    ...
    ...    **A day in the past, deliberately.** The service refuses a period
    ...    that has not finished — care that has not happened cannot be
    ...    invoiced — so the reference day is well behind today whatever the
    ...    configured periodicity is.
    ...
    ...    Tolerates a period that has already been billed: the guard makes a
    ...    re-run a no-op, which is exactly what the idempotency test relies on.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${reference}=    The Day Being Billed
    ${body}=    Create Dictionary    reference_date=${reference}
    ${response}=    POST
    ...    ${API_URL}/api/v1/bills/runs
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=202
    ${run_id}=    Set Variable    ${response.json()}[id]
    Wait Until Keyword Succeeds    ${BILLING_TIMEOUT}    2s
    ...    Billing Run Should Have Finished    ${run_id}
    ${finished}=    Billing Run As Stored    ${run_id}
    # Recorded so a test can assert on the invoices *this* run wrote rather
    # than on whatever the agency happens to hold: the duplicate guard makes a
    # second run a no-op, and "every invoice is unsent" would then be asserting
    # about documents an earlier pass had already validated and sent.
    Set Suite Variable    @{LAST_RUN_BILLS}    @{finished}[bill_ids]
    RETURN    ${{ len($finished["bill_ids"]) }}

Billing Run Should Have Finished
    [Documentation]    Assert a run has reached a terminal status.
    ...
    ...    Polled rather than asserted once, because the generation happens in a
    ...    worker after a broker round trip. A *partial* run counts as finished:
    ...    the invoices that could be written are written, and a client that
    ...    kept polling would wait for ever.
    [Arguments]    ${run_id}
    ${run}=    Billing Run As Stored    ${run_id}
    Should Contain Any    ${run}[status]    succeeded    partial    failed
    ...    msg=Billing run ${run_id} is still ${run}[status].

Billing Run As Stored
    [Documentation]    Return one generation run.
    [Arguments]    ${run_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/bills/runs/${run_id}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Invoices As Stored
    [Documentation]    Return the agency's invoices.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=200
    ${response}=    GET
    ...    ${API_URL}/api/v1/bills
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Invoice Count As Stored
    [Documentation]    Return how many invoices the agency holds.
    ${bills}=    Invoices As Stored
    RETURN    ${{ len($bills) }}

An Invoice Waiting To Be Validated
    [Documentation]    Return one invoice nobody has approved, or ``None``.
    ...
    ...    Returns rather than fails when there is none: an earlier run may
    ...    have validated everything, and the invoices are deliberately never
    ...    cleaned up — a number withdrawn from the series is the gap French
    ...    invoicing forbids.
    ${bills}=    Invoices As Stored
    ${waiting}=    Evaluate
    ...    [b for b in $bills if b["status"] == "to-be-validated"]
    ${found}=    Set Variable If    ${waiting}    ${waiting}[0]    ${None}
    RETURN    ${found}

Move Invoice To
    [Documentation]    Move an invoice one step along its lifecycle.
    [Arguments]    ${bill_id}    ${status}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    status=${status}
    PATCH
    ...    ${API_URL}/api/v1/bills/${bill_id}/status
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Invoice Status Should Be
    [Documentation]    Assert one invoice's current status.
    [Arguments]    ${bill_id}    ${expected}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/bills/${bill_id}
    ...    headers=${headers}
    ...    expected_status=200
    Should Be Equal    ${response.json()}[status]    ${expected}

Mail Catcher Message Count
    [Documentation]    Return how many messages Mailpit is holding.
    ${response}=    GET    ${MAILPIT_URL}/api/v1/messages    expected_status=200
    RETURN    ${response.json()}[messages_count]

The Mail Catcher Should Hold At Least
    [Documentation]    Assert Mailpit has received at least so many messages.
    [Arguments]    ${expected}
    ${count}=    Mail Catcher Message Count
    Should Be True    ${count} >= ${expected}
    ...    msg=Mailpit holds ${count} message(s); expected at least ${expected}.

Reload And Sign Out
    [Documentation]    Discard an unsaved form, then end the session.
    ...
    ...    The rules are never written by the test that uses this — it stops at
    ...    the refusal — so the form is simply thrown away rather than restored
    ...    over the API.
    Run Keyword And Ignore Error    Reload
    Sign Out

Set The Agency Periodicity To
    [Documentation]    Put the agency-wide rule on a known value.
    ...
    ...    So a per-customer test asserts a contrast rather than a coincidence:
    ...    a weekly invoice proves nothing where the agency itself bills weekly.
    ...    The suite teardown puts the rules back whatever happens.
    [Arguments]    ${periodicity}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    periodicity=${periodicity}
    ...    payment_terms_days=${ORIGINAL_BILLING}[payment_terms_days]
    ...    late_penalty_multiplier=${ORIGINAL_BILLING}[late_penalty_multiplier]
    ...    recovery_indemnity_eur=${ORIGINAL_BILLING}[recovery_indemnity_eur]
    ...    escompte_offered=${ORIGINAL_BILLING}[escompte_offered]
    PUT
    ...    ${API_URL}/api/v1/billing/settings
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Register A Household Billed
    [Documentation]    Register a customer, optionally on a rule of their own.
    ...
    ...    Registered fresh each time rather than reusing the book: a household
    ...    the earlier tests billed already has an invoice covering the period,
    ...    and a window overlapping one already issued is refused.
    [Arguments]    ${periodicity}
    ${suffix}=    Unique Suffix
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"first_name": "Facture", "last_name": "Qabill-${suffix}",
    ...    "phone_number": "+33600000199", "email": "bill-${suffix}@qa.simple-erp.fr",
    ...    "address": {"street": "12 rue de Rivoli", "postal_code": "75004",
    ...    "city": "Paris", "country": "France"},
    ...    "registration_status": "active"}
    ${created}=    POST
    ...    ${API_URL}/api/v1/customers
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=201
    ${customer_id}=    Set Variable    ${created.json()}[id]
    Append To List    ${QA_HOUSEHOLDS}    ${customer_id}
    IF    $periodicity is not None
        ${rule}=    Create Dictionary    periodicity=${periodicity}
        PATCH
        ...    ${API_URL}/api/v1/customers/${customer_id}/billing-periodicity
        ...    json=${rule}
        ...    headers=${headers}
        ...    expected_status=200
    END
    RETURN    ${customer_id}

Give Work Inside The Billed Period To
    [Documentation]    Sell and accept one visit on the day being billed.
    ...
    ...    The same shape as ``Ensure There Is Work To Bill`` but aimed at one
    ...    household, because a per-customer window is only observable on a
    ...    customer nothing else has billed.
    [Arguments]    ${customer_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${type_id}=    First Intervention Type
    ${suffix}=    Unique Suffix
    ${day}=    The Day Being Billed
    ${body}=    Catenate    SEPARATOR=
    ...    {"reference": "QA-GRAN-${suffix}",
    ...    "customer_id": "${customer_id}",
    ...    "lines": [{"name": "Aide a la toilette",
    ...    "intervention_type_id": "${type_id}",
    ...    "service_category": "necessity",
    ...    "service_date": "${day}",
    ...    "earliest_start": "09:00:00",
    ...    "latest_end": "12:00:00",
    ...    "duration_minutes": 120}]}
    ${quote}=    POST
    ...    ${API_URL}/api/v1/quotes
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=201
    POST
    ...    ${API_URL}/api/v1/quotes/${quote.json()}[id]/accept
    ...    headers=${headers}
    ...    expected_status=200

The Invoice Of
    [Documentation]    Return the one invoice issued to a household.
    [Arguments]    ${customer_id}
    ${bills}=    Invoices As Stored
    ${theirs}=    Evaluate
    ...    [b for b in $bills if b["customer_id"] == "${customer_id}"]
    Should Not Be Empty    ${theirs}
    ...    msg=The run issued no invoice to customer ${customer_id}.
    RETURN    ${theirs}[0]

Customer Billing Periodicity Of
    [Documentation]    Return a household's own rule, or ``None``.
    [Arguments]    ${customer_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers/${customer_id}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}[billing_periodicity]

Customer Should Follow The Agency
    [Documentation]    Assert a household carries no rule of its own.
    [Arguments]    ${customer_id}
    ${stored}=    Customer Billing Periodicity Of    ${customer_id}
    Should Be Equal    ${stored}    ${None}
    ...    msg=The override was not cleared; the customer is still billed ${stored}.

Open The File Of Customer
    [Documentation]    Open the customer book and the drawer on one household.
    ...
    ...    Searched for first: a household this run registered sits at the end
    ...    of a book of forty and the grid shows twenty-five to a page.
    [Arguments]    ${customer_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers/${customer_id}
    ...    headers=${headers}
    ...    expected_status=200
    Click    [data-testid="nav--customers"]
    Wait For Elements State    [data-testid="customers-grid"]    visible
    Fill Text    [data-testid="customer-search"]    ${response.json()}[last_name]
    Wait For Elements State
    ...    [data-testid="customers-grid"] .MuiDataGrid-row >> nth=0    visible
    ...    message=The customer book never listed the household this run registered.
    Click    [data-testid="customers-grid"] .MuiDataGrid-row >> nth=0
    Wait For Elements State    [data-testid="customer-billing-periodicity"]    visible
    ...    message=The customer file has no invoicing control.

Take A Screenshot On Failure
    [Documentation]    Capture the screen a failing test left behind.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
