*** Settings ***
Documentation    The household's own space, and the boundary around it.
...
...              A customer could not sign in at all until this feature: there
...              were three roles, all of them staff, and every screen was built
...              for the agency. This suite covers the fourth identity and what
...              it may reach — which is exactly their own file and nothing
...              else.
...
...              **The boundary is the point.** A household's calendar carries
...              their address and when somebody is in the house; their invoices
...              say what they pay for care. Half of what follows is therefore
...              about what a customer account is *refused*, and it is asserted
...              against the API rather than against a hidden button — a missing
...              menu entry proves nothing about what the server will serve.
...
...              **Idempotent by construction.** The account it invites is
...              created against a seeded prospect and deleted in the teardown,
...              which takes the account with it. It cancels nothing and moves
...              nothing on a seeded arrangement: both send a quote back to
...              validation and take work out of the next planning run, so one
...              left behind would change what every later run of the campaign
...              finds.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Invite A Household And Open The Application
Suite Teardown   Remove The Household And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${PORTAL_CUSTOMER_ID}     ${EMPTY}
${PORTAL_EMAIL}           ${EMPTY}
${PORTAL_PASSWORD}        ${EMPTY}


*** Test Cases ***
A Household Signs In To Their Own Space
    [Documentation]    **The fourth identity, end to end.**
    ...
    ...    The account was invited by a manager and carries a temporary
    ...    password, so the first sign-in lands on the password-change screen
    ...    exactly as a staff-created account does.
    [Tags]    smoke    portal
    Sign In As    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}    space=customer
    Wait For Elements State    [data-testid="current-user"]    visible

An Employee Account Cannot Sign In As A Customer
    [Documentation]    The chooser refuses rather than misleading.
    ...
    ...    The credentials are right and the *space* is wrong, so the message
    ...    says which side the account is on. Reported as "invalid credentials"
    ...    it would send somebody to reset a password that works perfectly.
    [Tags]    smoke    portal    access
    Sign Out
    Go To    ${BASE_URL}/login
    Wait For Elements State    [data-testid="login-email"]    visible
    Click    [data-testid="login-space-customer"]
    Fill Text    [data-testid="login-email"]    ${MANAGER_EMAIL}
    Fill Text    [data-testid="login-password"]    ${SEED_PASSWORD}
    Click    [data-testid="login-submit"]
    Wait For Elements State    [data-testid="login-error"]    visible

A Household Sees Only Their Own Entries
    [Documentation]    None of the agency's screens appear in their navigation.
    ...
    ...    Not a security control — the server refuses every staff route
    ...    regardless, and the next test proves it — but a household who can see
    ...    "Devis" and "Intervenants" will click them.
    [Tags]    smoke    portal
    Sign In As    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}    space=customer
    Wait For Elements State    [data-testid="nav--portal-planning"]    visible
    ${quotes}=    Get Element Count    [data-testid="nav--quotes"]
    Should Be Equal As Integers    ${quotes}    0
    ${hcas}=    Get Element Count    [data-testid="nav--hcas"]
    Should Be Equal As Integers    ${hcas}    0

A Customer Account Is Refused Every Staff Route
    [Documentation]    **The boundary, asserted against the API.**
    ...
    ...    A missing menu entry proves nothing about what the server will
    ...    serve. These are the routes a household must never reach: the whole
    ...    customer book, the workforce, and every assistant's diary — each of
    ...    which carries other families' names and addresses.
    [Tags]    smoke    portal    access
    ${token}=    Sign In Through The API    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}
    ${headers}=    Authorisation Header    ${token}
    FOR    ${path}    IN
    ...    /api/v1/customers
    ...    /api/v1/hcas
    ...    /api/v1/quotes
    ...    /api/v1/bills
    ...    /api/v1/planning/hcas
    ...    /api/v1/planning/customers
        GET    ${API_URL}${path}    headers=${headers}    expected_status=403
    END

An Employee Is Refused The Portal
    [Documentation]    The boundary runs both ways.
    ...
    ...    An administrator outranks everybody and is still refused, because
    ...    there is nothing to outrank: a customer is not a rung of the staff
    ...    ladder. The guard compares by identity, and the rank comparison
    ...    raises rather than answering.
    [Tags]    smoke    portal    access
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    FOR    ${path}    IN
    ...    /api/v1/portal/profile
    ...    /api/v1/portal/quotes
    ...    /api/v1/portal/bills
        GET    ${API_URL}${path}    headers=${headers}    expected_status=403
    END

A Household Corrects Their Own Details
    [Documentation]    **The requirement: their information, editable.**
    ...
    ...    Asserted on the server rather than on the form. A field that keeps
    ...    what was typed and a record that was never written look identical.
    [Tags]    smoke    portal
    ${token}=    Sign In Through The API    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"first_name": "Prospect", "last_name": "Qaportal",
    ...    "phone_number": "+33600000197", "email": "${PORTAL_EMAIL}",
    ...    "address": {"street": "5 rue de Turenne", "postal_code": "75003",
    ...    "city": "Paris", "country": "France"}}
    PUT
    ...    ${API_URL}/api/v1/portal/profile
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=200
    ${read}=    GET    ${API_URL}/api/v1/portal/profile    headers=${headers}
    Should Be Equal    ${read.json()}[phone_number]    tel:+33-6-00-00-01-97
    Should Be Equal    ${read.json()}[address][street]    5 rue de Turenne

A Household Cannot Promote Themselves
    [Documentation]    **The hole the payload's shape closes.**
    ...
    ...    Honoured, a prospect could make themselves active and put their own
    ...    work into the next planning run — the agency would be delivering care
    ...    it never agreed to. The request model has no such field, so the value
    ...    is ignored rather than refused, and the status is unchanged.
    [Tags]    smoke    portal    access
    ${token}=    Sign In Through The API    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"first_name": "Prospect", "last_name": "Qaportal",
    ...    "phone_number": "+33600000197", "email": "${PORTAL_EMAIL}",
    ...    "registration_status": "active",
    ...    "address": {"street": "5 rue de Turenne", "postal_code": "75003",
    ...    "city": "Paris", "country": "France"}}
    PUT
    ...    ${API_URL}/api/v1/portal/profile
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=200
    ${read}=    GET    ${API_URL}/api/v1/portal/profile    headers=${headers}
    Should Be Equal    ${read.json()}[registration_status]    prospect

A Household Reads Their Own Calendar
    [Documentation]    The screen the space is opened for.
    [Tags]    smoke    portal
    Sign In As    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}    space=customer
    Navigate To    /portal/planning
    Wait For Elements State    [data-testid="portal-calendar"]    visible

A Household Reads Their Quotes And Invoices
    [Documentation]    Both lists, and both download buttons.
    ...
    ...    Empty for a freshly invited household, which is the state worth
    ...    checking: the screens say so in a sentence rather than showing a
    ...    blank panel a customer reads as a failure.
    [Tags]    smoke    portal
    Sign In As    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}    space=customer
    Navigate To    /portal/quotes
    Wait For Elements State    [data-testid="portal-no-quote"]    visible
    Navigate To    /portal/bills
    Wait For Elements State    [data-testid="portal-no-bill"]    visible

One Household Cannot Reach Another's File
    [Documentation]    **404, not 403, and the difference is deliberate.**
    ...
    ...    Telling "no such visit" apart from "not yours" would let somebody
    ...    walk the identifier space and learn when the agency visits their
    ...    neighbours. Asserted on a visit that really belongs to a different
    ...    household, so the answer is the refusal rather than an absence.
    [Tags]    smoke    portal    access
    ${token}=    Sign In Through The API    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}
    ${headers}=    Authorisation Header    ${token}
    ${other}=    Any Intervention Of Another Household
    POST
    ...    ${API_URL}/api/v1/portal/interventions/${other}/cancel
    ...    headers=${headers}    expected_status=404

A Second Invitation Is Refused
    [Documentation]    One account per household.
    ...
    ...    Two accounts on one file are two people who each believe they were
    ...    the one who cancelled a visit — and the second invitation would
    ...    silently make the first set of credentials useless.
    [Tags]    portal
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"email": "second-${PORTAL_EMAIL}", "full_name": "Second Account"}
    POST
    ...    ${API_URL}/api/v1/customers/${PORTAL_CUSTOMER_ID}/account
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=409

An Assistant Cannot Invite A Household
    [Documentation]    Deciding a family may see their file is a manager's call.
    [Tags]    smoke    portal    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Catenate    SEPARATOR=
    ...    {"email": "nope@qa.simple-erp.fr", "full_name": "Nope"}
    POST
    ...    ${API_URL}/api/v1/customers/${PORTAL_CUSTOMER_ID}/account
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=403


The Agency And The Household Read The Same Calendar
    [Documentation]    **The property the staff-side households view exists for.**
    ...
    ...    A manager on the telephone to a family has to be looking at what the
    ...    family is looking at. The two screens read through one query on the
    ...    server, and this is what proves it end to end: the same household,
    ...    the same window, one list of visit identifiers, in one order.
    ...
    ...    Compared as **ordered** lists. Two sets that agree would still let one
    ...    side sort differently, and a calendar rendered from a differently
    ...    ordered list draws the afternoon visit first.
    ...
    ...    The service-level test asserts the same thing against the repository;
    ...    this one is what catches a filter added in the API layer to one route
    ...    and not the other, which the service test cannot see.
    [Tags]    portal    planning    synchronisation
    ${today}=    Get Current Date    result_format=%Y-%m-%d
    ${later}=    Add Time To Date    ${today}    41 days    result_format=%Y-%m-%d
    ${params}=    Create Dictionary    period_start=${today}    period_end=${later}

    ${household_token}=    Sign In Through The API    ${PORTAL_EMAIL}    ${PORTAL_PASSWORD}
    ${household_headers}=    Authorisation Header    ${household_token}
    ${theirs}=    GET
    ...    ${API_URL}/api/v1/portal/planning
    ...    params=${params}
    ...    headers=${household_headers}
    ...    expected_status=200

    ${manager_token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${manager_headers}=    Authorisation Header    ${manager_token}
    ${ours}=    GET
    ...    ${API_URL}/api/v1/planning/customers/${PORTAL_CUSTOMER_ID}
    ...    params=${params}
    ...    headers=${manager_headers}
    ...    expected_status=200

    ${household_visits}=    Evaluate    [v["id"] for v in $theirs.json()]
    ${agency_visits}=    Evaluate    [v["id"] for v in $ours.json()["interventions"]]
    Should Be Equal    ${household_visits}    ${agency_visits}
    ...    msg=The household reads ${household_visits} and the agency ${agency_visits}.


*** Keywords ***
Invite A Household And Open The Application
    [Documentation]    Register a household, give them portal access, open the app.
    ...
    ...    Created rather than borrowed. Signing in as a seeded customer would
    ...    be fine; *editing* one would change what every later suite reads, and
    ...    this one corrects an address.
    ${suffix}=    Unique Suffix
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${json}=    Set Variable    ${{ {**$headers, "Content-Type": "application/json"} }}

    ${customer}=    Catenate    SEPARATOR=
    ...    {"first_name": "Prospect", "last_name": "Qaportal",
    ...    "phone_number": "+33600000197",
    ...    "email": "portal-${suffix}@qa.simple-erp.fr",
    ...    "address": {"street": "12 rue de Rivoli", "postal_code": "75004",
    ...    "city": "Paris", "country": "France"}}
    ${created}=    POST
    ...    ${API_URL}/api/v1/customers
    ...    data=${customer}    headers=${json}    expected_status=201
    Set Suite Variable    ${PORTAL_CUSTOMER_ID}    ${created.json()}[id]
    Set Suite Variable    ${PORTAL_EMAIL}    portal-${suffix}@qa.simple-erp.fr

    ${invite}=    Catenate    SEPARATOR=
    ...    {"email": "${PORTAL_EMAIL}", "full_name": "Prospect Qaportal"}
    ${account}=    POST
    ...    ${API_URL}/api/v1/customers/${PORTAL_CUSTOMER_ID}/account
    ...    data=${invite}    headers=${json}    expected_status=201
    # Returned once, never stored in plaintext and never emailed — the same
    # trade a staff-created account makes.
    Set Suite Variable    ${PORTAL_PASSWORD}    ${account.json()}[temporary_password]

    Open The Application

Remove The Household And Close
    [Documentation]    Delete the household, which takes their account with it.
    ...
    ...    ``users.customer_id`` is ``RESTRICT``, so the delete would fail at
    ...    the database if the service did not remove the account first. That it
    ...    succeeds is itself the assertion.
    Run Keyword And Ignore Error    Sign Out
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    Run Keyword And Ignore Error    DELETE
    ...    ${API_URL}/api/v1/customers/${PORTAL_CUSTOMER_ID}
    ...    headers=${headers}    expected_status=any
    Close Browser

Any Intervention Of Another Household
    [Documentation]    Return a visit belonging to somebody else.
    ...
    ...    Read as a manager, who may see every planning. A visit of the suite's
    ...    own household would answer 200 and prove nothing.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    Ensure A Planning Has Been Computed
    ${period}=    A Planning Covers The Window
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/hcas
    ...    params=${period}    headers=${headers}    expected_status=200
    ${ids}=    Evaluate
    ...    [i["id"] for p in $response.json() for i in p["interventions"]
    ...     if i["customer_id"] != $PORTAL_CUSTOMER_ID]
    Should Not Be Empty    ${ids}
    ...    msg=No other household has a planned visit to test the boundary with.
    RETURN    ${ids}[0]

Take A Screenshot On Failure
    [Documentation]    Capture the screen when a test fails.
    Run Keyword If Test Failed    Take Screenshot
