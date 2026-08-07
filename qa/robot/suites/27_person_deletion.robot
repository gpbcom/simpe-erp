*** Settings ***
Documentation    Removing a person, and what the planning does about it.
...
...              Two rules are proved here. A deletion is **confirmed before it
...              happens, with its cost on screen** — a customer's dialog
...              counts the quotes that will go with them, because a
...              confirmation that does not say what it destroys is one nobody
...              reads. And a deletion **replans what the person was due**, in
...              a run scoped to their own remaining days rather than to a
...              fixed window.
...
...              Both fixtures are created by this run and removed by it, so
...              nothing seeded is touched. That matters more here than
...              anywhere else in the campaign: every other suite edits, and
...              this one destroys.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Customer File
Suite Teardown   Remove Whatever This Run Left And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
# Filled in by the setup, so two runs against one stack cannot collide.
${QA_SUFFIX}            ${EMPTY}
${QA_CUSTOMER_ID}       ${EMPTY}
${QA_CUSTOMER_NAME}     ${EMPTY}
${QA_HCA_ID}            ${EMPTY}


*** Test Cases ***
Every Customer Row Offers A Deletion
    [Documentation]    "All people may be deleted" has to be reachable.
    [Tags]    smoke    deletion
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible
    Find The QA Customer
    Wait For Elements State
    ...    [data-testid="delete-customer-${QA_CUSTOMER_ID}"]    visible

The Dialog Says What Will Be Destroyed
    [Documentation]    A confirmation that does not name its cost is not read.
    ...
    ...    The count is fetched before anything is removed, and it is the
    ...    number of quotes that go *with* the customer — the change this
    ...    feature made, and the one worth being told about. Stopping a
    ...    customer remains the reversible alternative, which the warning says.
    [Tags]    smoke    deletion
    Open The Delete Dialog For The QA Customer
    Wait For Elements State    [data-testid="delete-customer-counts"]    visible
    ${counts}=    Get Text    [data-testid="delete-customer-counts"]
    Should Match Regexp    ${counts}    \\d
    [Teardown]    Click    [data-testid="cancel-delete-customer"]

Cancelling Destroys Nothing
    [Documentation]    A manager who backs out has backed out.
    ...
    ...    Asserted through the API, because a grid that has not refetched
    ...    would look unchanged either way.
    [Tags]    deletion
    Open The Delete Dialog For The QA Customer
    Click    [data-testid="cancel-delete-customer"]
    Sleep    1s
    ${customer}=    The QA Customer
    Should Not Be Equal    ${customer}    ${None}
    ...    msg=Cancelling the dialog deleted the customer anyway.

Deleting A Customer Takes Their Quotes With Them
    [Documentation]    A quote names one customer and means nothing without them.
    ...
    ...    This used to be a refusal, and the change is deliberate: stopping a
    ...    customer is still right for one who was really served and has left,
    ...    but the refusal left no way at all to remove a household entered by
    ...    mistake — or the fixtures a campaign like this one is obliged to
    ...    clean up after itself.
    [Tags]    smoke    deletion
    ${quotes_before}=    Quotes Of The QA Customer
    Should Not Be Empty    ${quotes_before}
    ...    msg=The fixture has no quote, so the cascade is not being tested.

    Open The Delete Dialog For The QA Customer
    Click    [data-testid="confirm-delete-customer"]
    Sleep    3s

    ${customer}=    The QA Customer
    Should Be Equal    ${customer}    ${None}
    ...    msg=The customer survived their own deletion.
    Every Quote Should Be Gone    ${quotes_before}

The Grid Refetches After The Deletion
    [Documentation]    A row that lingers is a row somebody clicks again.
    [Tags]    deletion
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible
    Fill Text    [data-testid="customer-search"]    ${QA_CUSTOMER_NAME}
    Sleep    2s
    ${rows}=    Get Element Count    [data-testid="customers-grid"] .MuiDataGrid-row
    Should Be Equal As Integers    ${rows}    0
    [Teardown]    Clear The Customer Search

Every Assistant Row Offers A Deletion
    [Documentation]    The workforce half of the same rule.
    [Tags]    smoke    deletion
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    Find The QA Assistant
    Wait For Elements State    [data-testid="delete-hca-${QA_HCA_ID}"]    visible

The Assistant Dialog Warns That The Account Goes Too
    [Documentation]    An account naming a record that is gone cannot sign in usefully.
    ...
    ...    It cannot pass the row-level planning check and cannot be repaired
    ...    from any screen, so it is removed with the record rather than left
    ...    behind — which is what the foreign key used to prevent by refusing
    ...    the whole deletion.
    [Tags]    smoke    deletion
    Open The Delete Dialog For The QA Assistant
    Wait For Elements State    [data-testid="delete-hca-dialog"]    visible
    ${warning}=    Get Text    [data-testid="delete-hca-dialog"]
    Should Not Be Empty    ${warning}
    [Teardown]    Click    [data-testid="cancel-delete-hca"]

Deleting An Assistant Removes Their Account
    [Documentation]    The cascade, asserted on the thing that used to block it.
    [Tags]    smoke    deletion
    ${account_before}=    Account Of The QA Assistant
    Should Not Be Equal    ${account_before}    ${None}
    ...    msg=The fixture has no account, so the cascade is not being tested.

    Open The Delete Dialog For The QA Assistant
    Click    [data-testid="confirm-delete-hca"]
    Sleep    3s

    ${assistant}=    The QA Assistant
    Should Be Equal    ${assistant}    ${None}
    ...    msg=The assistant survived their own deletion.
    ${account_after}=    Account Of The QA Assistant
    Should Be Equal    ${account_after}    ${None}
    ...    msg=The sign-in account outlived the record it names.

A Deletion With Nothing To Replan Queues No Run
    [Documentation]    204, not 202, and the run list does not grow.
    ...
    ...    Queueing a run that would place the same visits in the same slots
    ...    costs thirty seconds of a worker and makes the calendar flicker for
    ...    no reason. The fixture this run made has no future visit, so the
    ...    right answer is silence.
    [Tags]    smoke    deletion    planning
    ${runs_before}=    Planning Run Count
    ${spare}=    Create A Spare Customer
    ${response}=    Delete A Customer Through The API    ${spare}
    Should Be Equal As Integers    ${response.status_code}    204
    Should Be Equal    ${response.text}    ${EMPTY}

    ${runs_after}=    Planning Run Count
    Should Be Equal As Integers    ${runs_before}    ${runs_after}
    ...    msg=A replan was queued for somebody with no future work.

The Last Administrator Cannot Be Deleted Through The Cascade
    [Documentation]    The account service's own refusals still apply.
    ...
    ...    Removing an assistant reaches ``AuthService.delete_account`` for the
    ...    account bound to them, so its guards are the ones in force — an
    ...    agency with no administrator cannot appoint one, and the mistake is
    ...    unrecoverable through the product. Sent by hand: no screen offers
    ...    this, and the rule must hold anyway.
    [Tags]    deletion    security
    ${admin}=    The Seeded Administrator
    ${hca_id}=    Set Variable    ${admin}[hca_id]
    Skip If    '${hca_id}' == 'None'
    ...    The seeded administrator holds no assistant record, so this path is unreachable.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    DELETE
    ...    ${API_URL}/api/v1/hcas/${hca_id}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    409


*** Keywords ***
Open The Customer File
    ${suffix}=    Unique Suffix
    Set Suite Variable    ${QA_SUFFIX}    ${suffix}
    Set Suite Variable    ${QA_CUSTOMER_NAME}    QASupprime${suffix}
    Build The Fixtures
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible

Manager Headers
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    RETURN    ${headers}

Admin Headers
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    RETURN    ${headers}

Build The Fixtures
    [Documentation]    Create the customer and the assistant this run destroys.
    ...
    ...    Through the API, and created fresh rather than borrowed from the
    ...    seed. Every other suite in this campaign edits; this one deletes,
    ...    and a suite that deletes seeded data is a suite that breaks every
    ...    suite after it.
    ${headers}=    Manager Headers
    ${customer}=    Create The QA Customer    ${headers}
    Set Suite Variable    ${QA_CUSTOMER_ID}    ${customer}[id]
    Give The QA Customer A Quote    ${headers}    ${customer}[id]
    ${assistant}=    Create The QA Assistant    ${headers}
    Set Suite Variable    ${QA_HCA_ID}    ${assistant}[id]
    Give The QA Assistant An Account    ${assistant}[id]

Create The QA Customer
    [Documentation]    Store a customer this run owns, and return them.
    [Arguments]    ${headers}
    ${body}=    Create Dictionary
    ...    first_name=Client
    ...    last_name=${QA_CUSTOMER_NAME}
    ...    phone_number=+33612345678
    ...    email=${QA_CUSTOMER_NAME.lower()}@qa.simple-erp.fr
    ...    registration_status=active
    ${address}=    Create Dictionary
    ...    street=12 rue de Rivoli
    ...    postal_code=75004
    ...    city=Paris
    Set To Dictionary    ${body}    address=${address}
    ${response}=    POST
    ...    ${API_URL}/api/v1/customers
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=201
    RETURN    ${response.json()}

Create A Spare Customer
    [Documentation]    Store a second customer, with no quote and no visit.
    ...
    ...    The 204 path needs somebody the planner has never placed, which the
    ...    quoted fixture above is not.
    ${headers}=    Manager Headers
    ${body}=    Create Dictionary
    ...    first_name=Client
    ...    last_name=QASansDevis${QA_SUFFIX}
    ...    phone_number=+33612345679
    ...    email=qasansdevis${QA_SUFFIX}@qa.simple-erp.fr
    ...    registration_status=active
    ${address}=    Create Dictionary
    ...    street=14 rue de Rivoli
    ...    postal_code=75004
    ...    city=Paris
    Set To Dictionary    ${body}    address=${address}
    ${response}=    POST
    ...    ${API_URL}/api/v1/customers
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=201
    RETURN    ${response.json()}[id]

Give The QA Customer A Quote
    [Documentation]    Write one quote for them, so the cascade has something to take.
    [Arguments]    ${headers}    ${customer_id}
    ${type_id}=    First Intervention Type
    ${service_date}=    Get Current Date    increment=14 days    result_format=%Y-%m-%d
    ${line}=    Create Dictionary
    ...    name=Aide a la toilette
    ...    intervention_type_id=${type_id}
    ...    service_category=necessity
    ...    service_date=${service_date}
    ...    earliest_start=09:00:00
    ...    latest_end=12:00:00
    ...    duration_minutes=${60}
    ${lines}=    Create List    ${line}
    ${body}=    Create Dictionary
    ...    reference=QA-DEL-${QA_SUFFIX}
    ...    customer_id=${customer_id}
    ...    lines=${lines}
    POST
    ...    ${API_URL}/api/v1/quotes
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=201

Create The QA Assistant
    [Documentation]    Store an assistant this run owns, and return them.
    [Arguments]    ${headers}
    ${company_id}=    The Seeded Company Id
    ${address}=    Create Dictionary
    ...    street=5 avenue de la Gare
    ...    postal_code=75012
    ...    city=Paris
    ${body}=    Create Dictionary
    ...    first_name=Intervenant
    ...    last_name=QASupprime${QA_SUFFIX}
    ...    phone_number=+33612345670
    ...    email=qahca${QA_SUFFIX}@qa.simple-erp.fr
    ...    company_id=${company_id}
    ...    contract_type=cdi
    Set To Dictionary    ${body}    address=${address}
    ${response}=    POST
    ...    ${API_URL}/api/v1/hcas
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=201
    RETURN    ${response.json()}

Give The QA Assistant An Account
    [Documentation]    Bind a sign-in account to them, so the cascade has something to take.
    [Arguments]    ${hca_id}
    ${headers}=    Admin Headers
    ${body}=    Create Dictionary
    ...    email=qahca${QA_SUFFIX}@qa.simple-erp.fr
    ...    full_name=Intervenant QA
    ...    hca_id=${hca_id}
    POST
    ...    ${API_URL}/api/v1/auth/accounts
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=201

The Seeded Company Id
    [Documentation]    Return the agency the seeded manager belongs to.
    ${headers}=    Manager Headers
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/account    headers=${headers}    expected_status=200
    RETURN    ${response.json()}[company_id]

The Seeded Administrator
    [Documentation]    Return the seeded administrator's account.
    ${headers}=    Admin Headers
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/account    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

The QA Customer
    [Documentation]    Return this run's customer, or ``None``.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    search=${QA_CUSTOMER_NAME}    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [c for c in $response.json() if c["last_name"]=="${QA_CUSTOMER_NAME}"]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

The QA Assistant
    [Documentation]    Return this run's assistant, or ``None``.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    search=QASupprime${QA_SUFFIX}    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [h for h in $response.json() if h["id"]=="${QA_HCA_ID}"]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

Account Of The QA Assistant
    [Documentation]    Return the account bound to this run's assistant, or ``None``.
    ${headers}=    Admin Headers
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/users
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [u for u in $response.json() if u["hca_id"]=="${QA_HCA_ID}"]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

Quotes Of The QA Customer
    [Documentation]    Return every quote written for this run's customer.
    ${headers}=    Manager Headers
    ${response}=    GET
    ...    ${API_URL}/api/v1/customers/${QA_CUSTOMER_ID}/quotes
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Every Quote Should Be Gone
    [Documentation]    Assert none of a customer's quotes outlived them.
    [Arguments]    ${quotes}
    ${headers}=    Manager Headers
    FOR    ${quote}    IN    @{quotes}
        ${response}=    GET
        ...    ${API_URL}/api/v1/quotes/${quote}[id]
        ...    headers=${headers}
        ...    expected_status=any
        Should Be Equal As Integers    ${response.status_code}    404
        ...    msg=Quote ${quote}[reference] outlived the customer it was written for.
    END

Planning Run Count
    [Documentation]    Return how many planning runs the agency has recorded.
    ${headers}=    Admin Headers
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${{ len($response.json()) }}

Delete A Customer Through The API
    [Documentation]    Remove a customer and return the raw response.
    ...
    ...    Raw, because the status is the assertion: 202 with a run to poll
    ...    when there was work to replan, 204 and no body when there was not.
    [Arguments]    ${customer_id}
    ${headers}=    Manager Headers
    ${response}=    DELETE
    ...    ${API_URL}/api/v1/customers/${customer_id}
    ...    headers=${headers}
    ...    expected_status=any
    RETURN    ${response}

Find The QA Customer
    Fill Text    [data-testid="customer-search"]    ${QA_CUSTOMER_NAME}
    Sleep    2s

Clear The Customer Search
    Fill Text    [data-testid="customer-search"]    ${EMPTY}
    Sleep    2s

Find The QA Assistant
    Fill Text    [data-testid="hca-search"]    QASupprime${QA_SUFFIX}
    Sleep    2s

Open The Delete Dialog For The QA Customer
    Navigate To    /customers
    Wait For Elements State    [data-testid="customers-grid"]    visible
    Find The QA Customer
    Click    [data-testid="delete-customer-${QA_CUSTOMER_ID}"]
    Wait For Elements State    [data-testid="delete-customer-dialog"]    visible

Open The Delete Dialog For The QA Assistant
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    Find The QA Assistant
    Click    [data-testid="delete-hca-${QA_HCA_ID}"]
    Wait For Elements State    [data-testid="delete-hca-dialog"]    visible

Remove Whatever This Run Left And Close
    [Documentation]    Delete this run's fixtures, and say so if one survives.
    ...
    ...    A belt-and-braces teardown: the tests remove both in the normal
    ...    path, and this catches the case where an earlier one failed. Nothing
    ...    here matches on a pattern — only on the identifiers this run
    ...    created — because a teardown that deleted by name prefix would take
    ...    a concurrent run's fixtures with it.
    ${status}    ${error}=    Run Keyword And Ignore Error    Strip This Run's Fixtures
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    This run's fixtures were left behind: ${error}
    END

Strip This Run's Fixtures
    [Documentation]    Remove the customer and the assistant, tolerating absence.
    ${manager}=    Manager Headers
    @{survivors}=    Create List
    IF    '${QA_CUSTOMER_ID}' != '${EMPTY}'
        ${customer}=    DELETE
        ...    ${API_URL}/api/v1/customers/${QA_CUSTOMER_ID}
        ...    headers=${manager}
        ...    expected_status=any
        IF    ${customer.status_code} not in [202, 204, 404]
            Append To List    ${survivors}    customer (HTTP ${customer.status_code})
        END
    END
    IF    '${QA_HCA_ID}' != '${EMPTY}'
        ${assistant}=    DELETE
        ...    ${API_URL}/api/v1/hcas/${QA_HCA_ID}
        ...    headers=${manager}
        ...    expected_status=any
        IF    ${assistant.status_code} not in [202, 204, 404]
            Append To List    ${survivors}    assistant (HTTP ${assistant.status_code})
        END
    END
    Should Be Empty    ${survivors}    msg=@{survivors}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
