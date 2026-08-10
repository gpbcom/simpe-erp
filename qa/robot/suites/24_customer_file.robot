*** Settings ***
Documentation    The customer's file, and the decisions taken from it.
...
...              "Bénéficiaires" sat in the navigation for a long time with no
...              screen behind it: the click fell through to the catch-all and
...              redirected home, which reads as the click not registering.
...              This suite covers the screen that now answers it, how the book
...              is narrowed, and the three decisions taken from a file —
...              promoting a prospect into the planning, ending an arrangement
...              early, and letting one renew itself.
...
...              **Promotion is the one with teeth.** A prospect may hold
...              accepted, priced, perfectly routable work that every planning
...              run deliberately leaves out; promoting them is what enters it
...              into the next one, so the promoted status is asserted on the
...              server rather than on the chip.
...
...              **Idempotent by construction.** Every quote it interrupts or
...              renews is one it created, deleted by identifier in the
...              teardown. It never touches a seeded arrangement: an
...              interruption reprices a quote and removes work from the next
...              planning run, so one left behind would change what every later
...              run of the campaign finds.

Library          Browser
Library          Collections
Library          DateTime
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Customer Screen
Suite Teardown   Remove The Arrangements And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
@{CREATED_QUOTE_IDS}
@{CREATED_CUSTOMER_IDS}
${CUSTOMER_ID}        ${EMPTY}
${CUSTOMER_NAME}      ${EMPTY}


*** Test Cases ***
Beneficiaires Is In The Navigation And Reaches A Screen
    [Documentation]    **The dead entry, now with something behind it.**
    ...
    ...    Asserted as a click that lands, not as an entry that exists: the
    ...    entry existed for weeks while the click went nowhere.
    [Tags]    smoke    navigation    customers
    Wait For Elements State    [data-testid="nav--customers"]    visible
    Click    [data-testid="nav--customers"]
    Wait For Elements State    [data-testid="customers-grid"]    visible
    ${url}=    Get Url
    Should End With    ${url}    /customers

An Assistant Has No Such Entry
    [Documentation]    The whole agency's book is a manager's screen.
    ...
    ...    An assistant has their own portfolio at ``/me/customers``, scoped to
    ...    the households they visit. This one lists every family the agency
    ...    serves.
    [Tags]    smoke    customers    access
    Sign Out
    Sign In As    ${ASSISTANT_EMAIL}
    ${entry}=    Get Element Count    [data-testid="nav--customers"]
    Should Be Equal As Integers    ${entry}    0
    [Teardown]    Return To The Manager And The Customer Screen

The Book Can Be Searched
    [Documentation]    Forty households, and a manager looking for one.
    [Tags]    smoke    customers
    ${before}=    Get Element Count    [data-testid="customers-grid"] .MuiDataGrid-row
    Should Be True    ${before} > 0
    Fill Text    [data-testid="customer-search"]    ${CUSTOMER_NAME}
    Sleep    1s
    ${after}=    Get Element Count    [data-testid="customers-grid"] .MuiDataGrid-row
    Should Be True    ${after} <= ${before}
    Should Be True    ${after} > 0
    [Teardown]    Clear The Search

A Beneficiary Can Be Registered From The Book
    [Documentation]    **The requirement: a way to add a beneficiary.**
    ...
    ...    The screen listed forty households and offered no way to record a
    ...    forty-first, so a manager taking a telephone enquiry had to leave the
    ...    application. The control sits beside the search on purpose: looking
    ...    the family up is what proves they are not already on file.
    ...
    ...    Asserted on the server rather than on the grid. A row that appears
    ...    because the dialog put it there optimistically and a record that was
    ...    never written is the failure worth catching.
    ...
    ...    Idempotent: the customer is named with this run's suffix and deleted
    ...    by identifier in the teardown. It is quoted for nothing, so the
    ...    delete is accepted.
    [Tags]    smoke    customers
    ${suffix}=    Unique Suffix
    ${surname}=    Set Variable    Qatest-${suffix}
    Click    [data-testid="add-customer"]
    Wait For Elements State    [data-testid="customer-dialog"]    visible

    Fill Text    [data-testid="customer-first-name"]     Camille
    Fill Text    [data-testid="customer-last-name"]      ${surname}
    Fill Text    [data-testid="customer-phone-number"]   +33600000199
    Fill Text    [data-testid="customer-email"]          ${suffix}@qa.simple-erp.fr
    Fill Text    [data-testid="customer-street"]         12 rue de Rivoli
    Fill Text    [data-testid="customer-postal-code"]    75004
    Fill Text    [data-testid="customer-city"]           Paris
    Click    [data-testid="save-customer"]
    Wait For Elements State    [data-testid="customer-dialog"]    detached

    ${stored}=    Wait Until Keyword Succeeds    10s    1s
    ...    Customer Stored Under    ${surname}
    Append To List    ${CREATED_CUSTOMER_IDS}    ${stored}[id]
    # A prospect, not a customer. The agency has taken their details, not
    # agreed to serve them, and nothing is scheduled until somebody says so.
    Should Be Equal    ${stored}[registration_status]    prospect
    Should Be Equal    ${stored}[address][city]    Paris
    [Teardown]    Clear The Search

An Assistant Cannot Register A Beneficiary
    [Documentation]    The agency's book is a manager's to add to.
    ...
    ...    Sent by hand rather than asserted on a hidden button: the control is
    ...    absent from an assistant's screen because the whole entry is, and a
    ...    missing button proves nothing about what the API accepts.
    [Tags]    smoke    customers    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"first_name": "Camille", "last_name": "Refuse",
    ...    "phone_number": "+33600000199", "email": "refuse@qa.simple-erp.fr",
    ...    "address": {"street": "12 rue de Rivoli", "postal_code": "75004",
    ...    "city": "Paris", "country": "France"}}
    POST
    ...    ${API_URL}/api/v1/customers
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=403

A Search That Matches Nobody Says So
    [Documentation]    A sentence, not an empty grid.
    [Tags]    customers    empty-state
    Fill Text    [data-testid="customer-search"]    ZZZ-nobody-ZZZ
    Wait For Elements State    [data-testid="no-customer"]    visible
    [Teardown]    Clear The Search

The File Shows Everything Held About The Person
    [Documentation]    **The requirement: all of a beneficiary's information.**
    ...
    ...    A file that shows a subset leaves the manager to go and find the
    ...    rest, which is the job this screen exists to save.
    [Tags]    smoke    customers
    Open The File Of The Fixture Customer
    FOR    ${field}    IN
    ...    detail-phone    detail-email    detail-address
    ...    detail-created    detail-updated    detail-status
        Wait For Elements State    [data-testid="${field}"]    visible
        ...    message=${field} is missing from the customer's file.
    END
    [Teardown]    Close The File

The File Lists The Arrangements Being Delivered
    [Documentation]    **What are we doing for them at the moment?**
    ...
    ...    The question the screen is opened to answer. The fixture quote is
    ...    accepted, so it belongs under the ongoing heading rather than in the
    ...    history below it.
    [Tags]    smoke    customers    quotes
    Open The File Of The Fixture Customer
    Wait For Elements State    [data-testid="ongoing-quotes"]    visible
    Wait For Elements State    [data-testid="arrangement-${FIXTURE_REFERENCE}"]
    ...    visible
    Get Text    [data-testid="arrangement-total-${FIXTURE_REFERENCE}"]    !=    ${EMPTY}
    [Teardown]    Close The File

An Arrangement Can Be Set To Renew Itself
    [Documentation]    The switch beside the arrangement it acts on.
    ...
    ...    Asserted on the server rather than on the switch: a control that
    ...    moves and a flag that does not is the failure worth catching.
    [Tags]    smoke    customers    renewal
    Open The File Of The Fixture Customer
    Click    [data-testid="auto-renew-${FIXTURE_REFERENCE}"]
    Wait Until Keyword Succeeds    10s    1s
    ...    Auto Renewal Should Be    ${FIXTURE_QUOTE_ID}    ${True}
    [Teardown]    Close The File

Renewal Is A Flag, Not An Immediate Act
    [Documentation]    Nothing is written until the arrangement expires.
    ...
    ...    The fixture is valid for another month, so a renewal sweep must
    ...    leave it alone. Without this, turning the switch on would create a
    ...    second billable quote the same afternoon.
    [Tags]    smoke    renewal
    ${before}=    Quotes For The Fixture Customer
    Run The Renewal Sweep
    ${after}=    Quotes For The Fixture Customer
    Should Be Equal As Integers    ${after}    ${before}
    ...    msg=A quote that has not expired was renewed anyway.

The Renewal Sweep Can Be Run Twice Without Billing Twice
    [Documentation]    **The property that lets this go on a timer.**
    ...
    ...    Two workers waking together, a retry after a partial failure, or a
    ...    manager pressing the button because the timer looked stuck — each
    ...    must leave the same number of quotes behind.
    [Tags]    smoke    renewal
    ${before}=    Quotes For The Fixture Customer
    Run The Renewal Sweep
    Run The Renewal Sweep
    ${after}=    Quotes For The Fixture Customer
    Should Be Equal As Integers    ${after}    ${before}

An Arrangement Can Be Ended On A Chosen Day
    [Documentation]    **The requirement: interrupt at a certain date.**
    ...
    ...    Run last of the arrangement tests, because it is the one that
    ...    changes what the fixture delivers. The end date is the first of its
    ...    two service days, so exactly one visit survives.
    [Tags]    smoke    customers    interruption
    Open The File Of The Fixture Customer
    Fill Text    [data-testid="interrupt-date-${FIXTURE_REFERENCE}"]    ${FIRST_DAY}
    Click    [data-testid="interrupt-${FIXTURE_REFERENCE}"]
    Wait For Elements State
    ...    [data-testid="arrangement-ends-${FIXTURE_REFERENCE}"]    visible

    ${stored}=    Quote As Stored    ${FIXTURE_QUOTE_ID}
    Should Be Equal    ${stored}[interrupted_on]    ${FIRST_DAY}
    [Teardown]    Close The File

Ending It Early Shortens The Price
    [Documentation]    **If a quote is shortened, the price follows.**
    ...
    ...    Two identical visits cut to one, so the total halves. Asserted as a
    ...    ratio of the stored amounts rather than against a figure: the agency
    ...    rate is configuration, and a hard-coded total would go stale.
    [Tags]    smoke    interruption    pricing
    ${stored}=    Quote As Stored    ${FIXTURE_QUOTE_ID}
    ${lines}=    Get Length    ${stored}[lines]
    Should Be Equal As Integers    ${lines}    2
    ...    msg=The cancelled visit was deleted; it should stay on the quote.

    ${counted}=    Evaluate    sum(a["line_count"] for a in $stored["aggregates"])
    Should Be Equal As Integers    ${counted}    1
    ...    msg=The total still counts ${counted} visit(s) after the interruption.

The Cancelled Visit Stays On The Document
    [Documentation]    So the quote can answer why the invoice came in lower.
    ...
    ...    A family asking that needs to see both figures. Deleting the visit
    ...    would leave nothing to answer with.
    [Tags]    smoke    interruption
    ${stored}=    Quote As Stored    ${FIXTURE_QUOTE_ID}
    ${priced}=    Evaluate
    ...    [line for line in $stored["lines"] if line["total_ttc"] is not None]
    Length Should Be    ${priced}    2
    ...    msg=A cancelled visit lost its amounts; the quote can no longer show it.

An Interruption Before The First Visit Is Refused
    [Documentation]    It would leave an accepted quote delivering nothing.
    ...
    ...    Sent by hand: the screen offers a date picker with no lower bound,
    ...    so this is the check that stops an arrangement being silenced rather
    ...    than rejected.
    [Tags]    smoke    interruption    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${long_ago}=    Get Current Date    increment=-365 days    result_format=%Y-%m-%d
    ${body}=    Create Dictionary    last_day=${long_ago}
    POST
    ...    ${API_URL}/api/v1/quotes/${FIXTURE_QUOTE_ID}/interrupt
    ...    json=${body}    headers=${headers}    expected_status=422

An Assistant Cannot End Somebody's Care
    [Documentation]    Ending an arrangement is a manager's decision.
    [Tags]    smoke    interruption    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    last_day=${FIRST_DAY}
    POST
    ...    ${API_URL}/api/v1/quotes/${FIXTURE_QUOTE_ID}/interrupt
    ...    json=${body}    headers=${headers}    expected_status=403

A Prospect Can Be Promoted To An Active Customer
    [Documentation]    **The requirement: promote, and only for a manager.**
    ...
    ...    Registered through the API rather than through the dialog, because
    ...    what is under test is the promotion and not the form.
    ...
    ...    The control is offered only on a prospect. One disabled on all ninety
    ...    rows buries the six that are waiting, so an active customer simply
    ...    does not have one.
    ...
    ...    Idempotent: the prospect is this run's, quoted for nothing, and
    ...    deleted by identifier in the teardown.
    [Tags]    smoke    customers    prospect
    ${prospect}=    Register A Prospect
    Append To List    ${CREATED_CUSTOMER_IDS}    ${prospect}[id]
    Open The File Of    ${prospect}[id]
    Wait For Elements State    [data-testid="customer-is-prospect"]    visible

    Click    [data-testid="promote-customer-${prospect}[id]"]
    Wait For Elements State    [data-testid="customer-is-prospect"]    detached

    # Asserted on the server. A chip that changed because the drawer re-read a
    # cache and a record that was never written look identical on screen.
    ${stored}=    Customer By Id    ${prospect}[id]
    Should Be Equal    ${stored}[registration_status]    active
    [Teardown]    Run Keywords    Close The File    AND    Clear The Search

An Active Customer Is Not Offered Promotion
    [Documentation]    There is nothing to promote them to.
    ...
    ...    Pressing it would be a 409, which is the right answer to a request
    ...    nobody should have been able to make. Absent is better than refused.
    [Tags]    customers    prospect
    Open The File Of The Fixture Customer
    ${offered}=    Get Element Count    [data-testid="customer-is-prospect"]
    Should Be Equal As Integers    ${offered}    0
    [Teardown]    Close The File

An Assistant Cannot Promote Anybody
    [Documentation]    Deciding the agency will serve a household is a
    ...    manager's call, and an administrator's.
    ...
    ...    Sent by hand: the control is absent from an assistant's screen only
    ...    because the whole entry is, and a missing button proves nothing
    ...    about what the API accepts.
    [Tags]    smoke    customers    prospect    access
    ${prospect}=    Register A Prospect
    Append To List    ${CREATED_CUSTOMER_IDS}    ${prospect}[id]
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    POST
    ...    ${API_URL}/api/v1/customers/${prospect}[id]/promote
    ...    headers=${headers}    expected_status=403

Promoting Somebody Twice Is Refused Rather Than Ignored
    [Documentation]    Two managers pressing at once.
    ...
    ...    A control that succeeds silently when it did nothing is one somebody
    ...    presses again and then wonders which press took effect.
    [Tags]    customers    prospect
    ${prospect}=    Register A Prospect
    Append To List    ${CREATED_CUSTOMER_IDS}    ${prospect}[id]
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    POST
    ...    ${API_URL}/api/v1/customers/${prospect}[id]/promote
    ...    headers=${headers}    expected_status=200
    POST
    ...    ${API_URL}/api/v1/customers/${prospect}[id]/promote
    ...    headers=${headers}    expected_status=409

The Book Can Be Narrowed To The Prospects
    [Documentation]    **The requirement: filter the book on its fields.**
    ...
    ...    The prospects tab is the one that matters: a prospect can be holding
    ...    accepted, priced work that no planning run will touch, and this is
    ...    how a manager finds them.
    [Tags]    smoke    customers    prospect    filters
    ${prospect}=    Register A Prospect
    Append To List    ${CREATED_CUSTOMER_IDS}    ${prospect}[id]
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible

    Click    [data-testid="customer-tab-prospect"]
    Wait For Elements State
    ...    [data-testid="customer-status-${prospect}[id]"]    visible
    # The filter is in the URL, so a narrowed book is a link somebody can send.
    ${url}=    Get Url
    Should Contain    ${url}    status=prospect
    # The fixture customer is active, so the prospects tab must not hold them.
    ${active}=    Get Element Count    [data-testid="customer-name-${CUSTOMER_ID}"]
    Should Be Equal As Integers    ${active}    0

    Click    [data-testid="customer-tab-active"]
    Wait For Elements State    [data-testid="customer-name-${CUSTOMER_ID}"]    visible
    [Teardown]    Clear The Search

A Town Filter Narrows The Book And Survives A Reload
    [Documentation]    The filters are URL state, not component state.
    ...
    ...    Reloaded, a filter held in a ``useState`` comes back cleared and the
    ...    manager is reading the whole book believing they are not.
    [Tags]    customers    filters
    Click    [data-testid="toggle-customer-filters"]
    Wait For Elements State    [data-testid="customer-filters"]    visible
    Fill Text    [data-testid="customer-filter-city"]    ZZZ-nowhere-ZZZ
    Wait For Elements State    [data-testid="no-customer"]    visible

    Reload
    Wait For Elements State    [data-testid="no-customer"]    visible
    ${url}=    Get Url
    Should Contain    ${url}    city=ZZZ-nowhere-ZZZ
    [Teardown]    Clear The Search


*** Keywords ***
Open The Customer Screen
    [Documentation]    Create the fixture arrangement, then open the browser.
    Build The Fixture Arrangement
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible

Build The Fixture Arrangement
    [Documentation]    Write and accept a two-visit quote for a real customer.
    ...
    ...    Accepted, because only an accepted arrangement is being delivered
    ...    and so only an accepted one can be ended. Created rather than
    ...    borrowed: interrupting reprices the quote and removes work from the
    ...    next planning run, and a seeded one left shortened would change what
    ...    every later run of the campaign finds.
    ${suffix}=    Unique Suffix
    ${customer_id}=    First Customer Of    ${ASSISTANT_EMAIL}
    ${type_id}=    First Intervention Type
    Set Suite Variable    ${CUSTOMER_ID}    ${customer_id}
    ${surname}=    Family Name Of The First Customer Of    ${ASSISTANT_EMAIL}
    Set Suite Variable    ${CUSTOMER_NAME}    ${surname}

    ${first}=    Get Current Date    increment=14 days    result_format=%Y-%m-%d
    ${second}=    Get Current Date    increment=21 days    result_format=%Y-%m-%d
    Set Suite Variable    ${FIRST_DAY}    ${first}

    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"reference": "QA-CARE-${suffix}",
    ...    "customer_id": "${customer_id}",
    ...    "lines": [
    ...    {"name": "Aide a la toilette", "intervention_type_id": "${type_id}",
    ...    "service_category": "necessity", "service_date": "${first}",
    ...    "earliest_start": "09:00:00", "latest_end": "12:00:00",
    ...    "duration_minutes": 120},
    ...    {"name": "Aide a la toilette", "intervention_type_id": "${type_id}",
    ...    "service_category": "necessity", "service_date": "${second}",
    ...    "earliest_start": "09:00:00", "latest_end": "12:00:00",
    ...    "duration_minutes": 120}]}
    ${created}=    POST
    ...    ${API_URL}/api/v1/quotes
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=201
    Set Suite Variable    ${FIXTURE_QUOTE_ID}    ${created.json()}[id]
    Set Suite Variable    ${FIXTURE_REFERENCE}    QA-CARE-${suffix}
    Append To List    ${CREATED_QUOTE_IDS}    ${created.json()}[id]

    POST
    ...    ${API_URL}/api/v1/quotes/${created.json()}[id]/accept
    ...    headers=${headers}    expected_status=200

Remove The Arrangements And Close
    [Documentation]    Delete this run's quotes and customers.
    ...
    ...    Successors are found by asking for them rather than assumed absent:
    ...    if a renewal ever did fire, the quote it wrote is this run's to
    ...    clean up too.
    ...
    ...    The customers go after the quotes, because a customer any quote names
    ...    is refused a delete — which is the right rule, and the wrong order
    ...    here would leave a fixture household in the book for ever.
    Run Keyword And Ignore Error    Collect Any Successors
    Remove The Quotes Created By This Run    @{CREATED_QUOTE_IDS}
    Run Keyword And Ignore Error    Remove The Customers Created By This Run
    Close The Application

Remove The Customers Created By This Run
    [Documentation]    Delete every customer this run registered.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    FOR    ${customer_id}    IN    @{CREATED_CUSTOMER_IDS}
        DELETE
        ...    ${API_URL}/api/v1/customers/${customer_id}
        ...    headers=${headers}    expected_status=any
    END

Customer Stored Under
    [Documentation]    Return the customer the server holds under a surname.
    [Arguments]    ${surname}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    search=${surname}    size=5
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers
    ...    params=${params}    headers=${headers}    expected_status=200
    Length Should Be    ${response.json()}    1
    ...    msg=The dialog reported success but stored no such customer.
    RETURN    ${response.json()}[0]

Collect Any Successors
    [Documentation]    Add any renewal of this run's quotes to the teardown list.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes
    ...    params=${params}    headers=${headers}    expected_status=200
    ${successors}=    Evaluate
    ...    [q["id"] for q in $response.json() if q.get("renewed_from_id") in $CREATED_QUOTE_IDS]
    FOR    ${quote_id}    IN    @{successors}
        Append To List    ${CREATED_QUOTE_IDS}    ${quote_id}
    END

Register A Prospect
    [Documentation]    Register a household through the API and return it.
    ...
    ...    They come back a prospect because that is the model's default —
    ...    asserted here rather than assumed, since every promotion test above
    ...    is meaningless if the fixture starts out active.
    ${suffix}=    Unique Suffix
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"first_name": "Prospect", "last_name": "Qatest-${suffix}",
    ...    "phone_number": "+33600000198", "email": "${suffix}@qa.simple-erp.fr",
    ...    "address": {"street": "12 rue de Rivoli", "postal_code": "75004",
    ...    "city": "Paris", "country": "France"}}
    ${response}=    POST
    ...    ${API_URL}/api/v1/customers
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=201
    Should Be Equal    ${response.json()}[registration_status]    prospect
    RETURN    ${response.json()}

Customer By Id
    [Documentation]    Return one customer as the server holds them.
    [Arguments]    ${customer_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers/${customer_id}
    ...    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Open The File Of
    [Documentation]    Open the drawer on one customer, finding them by name.
    ...
    ...    Searched for first: a household this run registered sits at the end
    ...    of a book of forty and the grid shows twenty-five to a page.
    [Arguments]    ${customer_id}
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible
    Fill Text    [data-testid="customer-search"]    Qatest
    Wait For Elements State    [data-testid="customer-name-${customer_id}"]    visible
    Click    [data-testid="customer-name-${customer_id}"]
    Wait For Elements State    [data-testid="customer-detail"]    visible

Open The File Of The Fixture Customer
    [Documentation]    Open the drawer on the customer the fixture is for.
    Navigate To    /customers
    Wait For Elements State    [data-testid="customer-name-${CUSTOMER_ID}"]    visible
    Click    [data-testid="customer-name-${CUSTOMER_ID}"]
    Wait For Elements State    [data-testid="customer-detail"]    visible

Close The File
    [Documentation]    Dismiss the drawer, whatever state it is in.
    Run Keyword And Ignore Error    Click    [data-testid="close-customer-detail"]
    Run Keyword And Ignore Error
    ...    Wait For Elements State    [data-testid="customer-detail"]    detached

Clear The Search
    [Documentation]    Put the grid back to the whole book.
    ...
    ...    The button rather than emptying the box: the box is one of eight
    ...    filters now, and a status tab left on would leave the next test
    ...    reading a narrowed book with nothing saying so. It is only rendered
    ...    when something is actually filtered, hence the ignored error.
    Run Keyword And Ignore Error    Click    [data-testid="clear-customer-filters"]
    Run Keyword And Ignore Error    Fill Text    [data-testid="customer-search"]    ${EMPTY}
    Sleep    0.5s

Return To The Manager And The Customer Screen
    [Documentation]    Sign back in as the manager and reopen the book.
    Sign Out
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible

Quote As Stored
    [Documentation]    Read a quote as the server currently holds it.
    [Arguments]    ${quote_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes/${quote_id}
    ...    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Auto Renewal Should Be
    [Documentation]    Assert a quote's renewal flag on the server.
    [Arguments]    ${quote_id}    ${expected}
    ${stored}=    Quote As Stored    ${quote_id}
    Should Be Equal    ${stored}[auto_renew]    ${expected}

Quotes For The Fixture Customer
    [Documentation]    Return how many quotes the fixture customer has.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers/${CUSTOMER_ID}/quotes
    ...    headers=${headers}    expected_status=200
    ${count}=    Get Length    ${response.json()}
    RETURN    ${count}

Run The Renewal Sweep
    [Documentation]    Ask the server to write successors for expired work.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    POST
    ...    ${API_URL}/api/v1/quotes/renewals/run
    ...    headers=${headers}    expected_status=200

Take A Screenshot On Failure
    [Documentation]    Keep the picture of whatever went wrong.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
