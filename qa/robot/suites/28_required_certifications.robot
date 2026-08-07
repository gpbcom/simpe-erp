*** Settings ***
Documentation    A service that requires a qualification, end to end.
...
...              This is the rule the whole feature exists for: an intervention
...              that needs a certification is given only to somebody who holds
...              it, and when nobody does the run **fails** rather than sending
...              an unqualified person. Failing is the intended answer —
...              sending somebody unqualified is worse than sending nobody, and
...              the failed run names the missing qualification so a manager
...              can hire, train, or correct the requirement.
...
...              The requirement is set on a catalogue entry this run creates,
...              never on a seeded one: a seeded service gated on a
...              qualification nobody holds would fail every planning run in
...              every suite after this.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Service Catalogue
Suite Teardown   Remove This Run's Service And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${QA_SUFFIX}        ${EMPTY}
${QA_TYPE_ID}       ${EMPTY}
${QA_TYPE_CODE}     ${EMPTY}
${QA_TYPE_NAME}     ${EMPTY}
${QA_CERT_CODE}     ${EMPTY}
${QA_CERT_LABEL}    ${EMPTY}
# The code the failure path is built on, and the fixtures it hangs off.
${QA_ORPHAN_CODE}   ${EMPTY}
${QA_CUSTOMER_ID}   ${EMPTY}
${QA_QUOTE_ID}      ${EMPTY}


*** Test Cases ***
A New Service Requires Nothing
    [Documentation]    The default that made the field safe to add.
    ...
    ...    A default that required something would have gated every service
    ...    already being sold behind a qualification nobody had been asked to
    ...    record — a migration failure wearing a solver's clothes.
    [Tags]    smoke    certifications    catalog
    ${service}=    The QA Service
    Should Be Empty    ${service}[required_certification_codes]

The Dialog Offers Every Recognised Qualification
    [Documentation]    The picker is fed by the catalogue, not by free text.
    ...
    ...    A typed requirement would match nobody and fail every run touching
    ...    it, with a diagnosis reading as a staffing problem rather than as
    ...    the typo it was.
    [Tags]    smoke    certifications    catalog
    Open The QA Service
    Wait For Elements State    [data-testid="type-certifications"]    visible
    ${options}=    Get Element Count    [data-testid="type-certifications"] option
    Should Be True    ${options} > 0
    [Teardown]    Click    [data-testid="cancel-type"]

A Requirement Set On The Screen Is Stored
    [Documentation]    The catalogue entry is where a service's requirement lives.
    [Tags]    smoke    certifications    catalog
    Open The QA Service
    Select Options By    [data-testid="type-certifications"]    value    ${QA_CERT_CODE}
    Click    [data-testid="save-type"]
    Sleep    2s

    ${service}=    The QA Service
    Should Contain    ${service}[required_certification_codes]    ${QA_CERT_CODE}

A Requirement Naming An Unknown Code Is Refused
    [Documentation]    The referential integrity a JSON column cannot have.
    ...
    ...    No foreign key can reach inside an array, so the check runs in the
    ...    service — and it answers 422 naming the offending code rather than
    ...    an integrity error naming a constraint. Sent by hand, because the
    ...    screen's picker cannot produce an unknown code and the rule must
    ...    hold for anything that can.
    [Tags]    smoke    certifications    validation    security
    ${headers}=    Manager Headers
    ${codes}=    Create List    CE-CODE-N-EXISTE-PAS
    ${body}=    Create Dictionary    required_certification_codes=${codes}
    ${response}=    PATCH
    ...    ${API_URL}/api/v1/intervention-types/${QA_TYPE_ID}
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be Equal As Integers    ${response.status_code}    422
    Should Contain    ${response.text}    CE-CODE-N-EXISTE-PAS

    ${service}=    The QA Service
    Should Not Contain
    ...    ${service}[required_certification_codes]    CE-CODE-N-EXISTE-PAS

A Quote Line Inherits The Service's Requirement
    [Documentation]    Null means "whatever the service requires", not "nothing".
    [Tags]    smoke    certifications    quotes
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quotes-grid"]    visible
    Click    [data-testid="new-quote"]
    Wait For Elements State    [data-testid="new-quote-dialog"]    visible
    Select Options By    [data-testid="new-quote-type-0"]    label    ${QA_TYPE_NAME}
    Sleep    1s
    # Inheriting is the default, and the chips say what is inherited: "this
    # visit needs DEAES" is something the operator should see before the
    # planner tells them nobody is qualified for it.
    Wait For Elements State
    ...    [data-testid="line-certification-0-${QA_CERT_CODE}"]    visible
    [Teardown]    Click    [data-testid="new-quote-cancel"]

A Line Can Be Taken Off The Service's Requirement
    [Documentation]    An empty override is a real answer, not a missing one.
    ...
    ...    "This hour needs no qualification at all" is the edit somebody makes
    ...    when the catalogue's default is wrong for one customer. Collapsing
    ...    it into "inherit" would silently reinstate the requirement they had
    ...    deliberately removed.
    [Tags]    certifications    quotes
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quotes-grid"]    visible
    Click    [data-testid="new-quote"]
    Wait For Elements State    [data-testid="new-quote-dialog"]    visible
    Select Options By    [data-testid="new-quote-type-0"]    label    ${QA_TYPE_NAME}
    Sleep    1s
    Click    [data-testid="line-certifications-inherit-0"]
    # Unticking hands the operator the inherited codes to edit, rather than an
    # empty list: they said "let me change this", not "require nothing".
    Wait For Elements State    [data-testid="line-certifications-0"]    visible
    [Teardown]    Click    [data-testid="new-quote-cancel"]

Work Nobody Is Qualified For Fails The Whole Run
    [Documentation]    The rule the feature exists for, driven to a real solve.
    ...
    ...    A run that cannot place everything **fails as a whole** rather than
    ...    storing a partial plan: a calendar missing three visits still looks
    ...    like a calendar, and the visits quietly dropped are the ones that end
    ...    with somebody waiting at their door. Failing is therefore the
    ...    intended answer, and it is non-destructive — the store is never
    ...    reached, so the week's existing plan survives untouched.
    ...
    ...    The service is gated on a code nobody holds and sold to a customer
    ...    this run created; both are stripped in the teardown.
    [Tags]    smoke    certifications    planning
    ${orphan}=    A Code Nobody Holds
    Skip If    '${orphan}' == '${EMPTY}'
    ...    Every catalogue qualification is held by somebody; the failure path is unreachable.

    Require The Orphan Code On This Run's Service    ${orphan}
    Sell This Run's Service To A Customer
    ${day}=    The Day This Run Sells Into
    Request A Planning For    ${day}
    Wait Until Keyword Succeeds    120s    2s    The Newest Run Has Finished

    ${run}=    Latest Run
    Should Be Equal    ${run}[status]    failed
    ...    msg=An unqualified assistant was scheduled on gated work.

The Failure Names The Missing Qualification
    [Documentation]    The message is the whole value of a failed run.
    ...
    ...    ``missing-certification`` is reported ahead of anything
    ...    geographical, and that ordering is the point: "nobody here holds
    ...    DEAES" names a hire, a training course or a requirement that was
    ...    wrong, while "out of radius" sends a manager to widen a radius that
    ...    was never the problem. The reason is folded into the run's own
    ...    message, so the record is enough to act on without re-running
    ...    anything.
    [Tags]    smoke    certifications    planning
    ${run}=    Latest Run
    Skip If    '${run}[status]' != 'failed'    The previous test did not fail a run.
    Should Contain    ${run}[error_message]    ${QA_ORPHAN_CODE}
    ...    msg=The failure did not say which qualification was missing.

The Failed Run Leaves The Existing Plan Alone
    [Documentation]    A refused plan is not a deleted one.
    ...
    ...    The completeness check raises before the store is reached, so the
    ...    agency keeps a working calendar while the problem is fixed. A run
    ...    that emptied the week on its way to reporting a failure would be
    ...    worse than no run at all.
    [Tags]    certifications    planning
    ${run}=    Latest Run
    Skip If    '${run}[status]' != 'failed'    The previous test did not fail a run.
    Should Be Equal    ${run}[scheduled_count]    ${None}
    ...    msg=A failed run wrote visits.

A Qualified Workforce Is Left To The Solver
    [Documentation]    The constraint narrows the pool; it does not empty it.
    ...
    ...    The counterpart to the failure above, and the reason the gate is
    ...    worth having: when somebody *does* hold the qualification, the work
    ...    is theirs rather than nobody's.
    [Tags]    certifications    planning
    ${holders}=    Assistants Holding The Requirement
    Should Not Be Empty    ${holders}
    ...    msg=No seeded assistant holds ${QA_CERT_CODE}; the constraint cannot be observed.
    ${workforce}=    The Whole Workforce
    Should Be True    ${{ len($holders) }} < ${{ len($workforce) }}
    ...    msg=Everybody holds ${QA_CERT_CODE}, so the requirement narrows nothing.


*** Keywords ***
Open The Service Catalogue
    ${suffix}=    Unique Suffix
    ${digits}=    Replace String    ${suffix}    -    ${EMPTY}
    Set Suite Variable    ${QA_SUFFIX}    ${suffix}
    Set Suite Variable    ${QA_TYPE_CODE}    QAS${digits}
    Set Suite Variable    ${QA_TYPE_NAME}    Prestation QA ${suffix}
    Choose A Seeded Qualification
    Create The QA Service
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="catalog-grid"]    visible

Manager Headers
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    RETURN    ${headers}

Choose A Seeded Qualification
    [Documentation]    Pick a catalogue entry somebody already holds.
    ...
    ...    Held by somebody, deliberately: a requirement nobody satisfies makes
    ...    every run touching it fail, and this suite's service is real enough
    ...    to be planned over.
    ${headers}=    Manager Headers
    ${response}=    GET
    ...    ${API_URL}/api/v1/certifications
    ...    headers=${headers}
    ...    expected_status=200
    ${entries}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${entries}
    ...    msg=The certification catalogue is empty; was the seeder run?
    ${workforce}=    The Whole Workforce
    ${held}=    Evaluate
    ...    {c["code"] for h in $workforce for c in h["certifications"] if c["code"]}
    ${common}=    Evaluate    [e for e in $entries if e["code"] in $held]
    ${chosen}=    Set Variable If    ${common}    ${common}[0]    ${entries}[0]
    Set Suite Variable    ${QA_CERT_CODE}    ${chosen}[code]
    Set Suite Variable    ${QA_CERT_LABEL}    ${chosen}[label]

The Whole Workforce
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Assistants Holding The Requirement
    [Documentation]    Return the assistants who hold this suite's code.
    ${workforce}=    The Whole Workforce
    ${holders}=    Evaluate
    ...    [h for h in $workforce if any(c["code"]=="${QA_CERT_CODE}" for c in h["certifications"])]
    RETURN    ${holders}

A Code Nobody Holds
    [Documentation]    Return a catalogue code no assistant holds, or empty.
    ${headers}=    Manager Headers
    ${response}=    GET
    ...    ${API_URL}/api/v1/certifications
    ...    headers=${headers}
    ...    expected_status=200
    ${workforce}=    The Whole Workforce
    ${held}=    Evaluate
    ...    {c["code"] for h in $workforce for c in h["certifications"] if c["code"]}
    ${orphans}=    Evaluate
    ...    [e["code"] for e in $response.json() if e["code"] not in $held]
    ${found}=    Set Variable If    ${orphans}    ${orphans}[0]    ${EMPTY}
    RETURN    ${found}

Create The QA Service
    [Documentation]    Store a catalogue entry this run owns, and remember it.
    ...
    ...    Never a seeded one. A seeded service gated on a qualification would
    ...    make every planning run in every later suite fail, which is the
    ...    hardest kind of failure to trace back to its cause.
    ${headers}=    Manager Headers
    ${body}=    Create Dictionary
    ...    name=${QA_TYPE_NAME}
    ...    code=${QA_TYPE_CODE}
    ...    service_category=necessity
    ...    is_active=${True}
    ${response}=    POST
    ...    ${API_URL}/api/v1/intervention-types
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=201
    Set Suite Variable    ${QA_TYPE_ID}    ${response.json()}[id]

The QA Service
    [Documentation]    Return this run's catalogue entry as the server holds it.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    size=500    include_inactive=true
    ${response}=    GET
    ...    ${API_URL}/api/v1/intervention-types
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [e for e in $response.json() if e["id"]=="${QA_TYPE_ID}"]
    Should Not Be Empty    ${matching}    msg=This run's service is missing.
    RETURN    ${matching}[0]

Open The QA Service
    [Documentation]    Find this run's entry on the catalogue grid and open it.
    Navigate To    /intervention-types
    Wait For Elements State    [data-testid="catalog-grid"]    visible
    Click    [data-testid="edit-type-${QA_TYPE_CODE}"]
    Wait For Elements State    [data-testid="type-dialog"]    visible

Remove This Run's Service And Close
    [Documentation]    Retire and strip this run's catalogue entry.
    ...
    ...    A service cannot be deleted — a quote issued last year still names
    ...    its type — so the requirement is cleared and the entry retired
    ...    instead. Clearing the requirement is the part that matters: an entry
    ...    left gated on a qualification would go on failing runs even retired,
    ...    because a quote already written against it still schedules.
    Run Keyword And Ignore Error    Remove This Run's Customer
    ${status}    ${error}=    Run Keyword And Ignore Error    Retire This Run's Service
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    This run's service was left requiring a qualification: ${error}
    END

Retire This Run's Service
    ${headers}=    Manager Headers
    ${none}=    Create List
    ${body}=    Create Dictionary
    ...    required_certification_codes=${none}
    ...    is_active=${False}
    IF    '${QA_TYPE_ID}' != '${EMPTY}'
        PATCH
        ...    ${API_URL}/api/v1/intervention-types/${QA_TYPE_ID}
        ...    json=${body}
        ...    headers=${headers}
        ...    expected_status=200
    END

Require The Orphan Code On This Run's Service
    [Documentation]    Gate this run's service on a qualification nobody holds.
    [Arguments]    ${code}
    Set Suite Variable    ${QA_ORPHAN_CODE}    ${code}
    ${headers}=    Manager Headers
    ${codes}=    Create List    ${code}
    ${body}=    Create Dictionary    required_certification_codes=${codes}
    PATCH
    ...    ${API_URL}/api/v1/intervention-types/${QA_TYPE_ID}
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

The Day This Run Sells Into
    [Documentation]    Return the day this run's work falls on.
    ${day}=    Get Current Date    increment=14 days    result_format=%Y-%m-%d
    RETURN    ${day}

Sell This Run's Service To A Customer
    [Documentation]    Create a customer and an accepted quote on the gated service.
    ...
    ...    Its own customer, never a seeded one: an accepted quote attached to
    ...    a seeded household would go on failing every planning run after this
    ...    suite, and the cause would be several suites away from the symptom.
    ${headers}=    Manager Headers
    ${address}=    Create Dictionary
    ...    street=12 rue de Rivoli
    ...    postal_code=75004
    ...    city=Paris
    ${customer}=    Create Dictionary
    ...    first_name=Client
    ...    last_name=QACertif${QA_SUFFIX}
    ...    phone_number=+33612345677
    ...    email=qacertif${QA_SUFFIX}@qa.simple-erp.fr
    ...    registration_status=active
    Set To Dictionary    ${customer}    address=${address}
    ${created}=    POST
    ...    ${API_URL}/api/v1/customers
    ...    json=${customer}
    ...    headers=${headers}
    ...    expected_status=201
    Set Suite Variable    ${QA_CUSTOMER_ID}    ${created.json()}[id]

    ${day}=    The Day This Run Sells Into
    ${line}=    Create Dictionary
    ...    name=Prestation QA sous condition
    ...    intervention_type_id=${QA_TYPE_ID}
    ...    service_category=necessity
    ...    service_date=${day}
    ...    earliest_start=09:00:00
    ...    latest_end=12:00:00
    ...    duration_minutes=${60}
    ${lines}=    Create List    ${line}
    ${body}=    Create Dictionary
    ...    reference=QA-CERT-${QA_SUFFIX}
    ...    customer_id=${created.json()}[id]
    ...    lines=${lines}
    ${quote}=    POST
    ...    ${API_URL}/api/v1/quotes
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=201
    Set Suite Variable    ${QA_QUOTE_ID}    ${quote.json()}[id]
    # ``send`` and not a status patch: a quote a manager writes by hand is one
    # they have already settled with the family, so sending lands it straight
    # in ``accepted`` — which is what makes it schedulable and therefore what
    # makes this suite's failure reachable at all.
    POST
    ...    ${API_URL}/api/v1/quotes/${quote.json()}[id]/send
    ...    headers=${headers}
    ...    expected_status=200

Request A Planning For
    [Documentation]    Ask for a run over one day.
    ...
    ...    One day, not the seeded week: the narrower the period, the fewer
    ...    unrelated visits the solver has to place, and the sooner the failure
    ...    this suite is waiting for arrives.
    [Arguments]    ${day}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    period_start=${day}    period_end=${day}
    POST
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=202

Latest Run
    [Documentation]    Return the most recent planning run.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=20
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${runs}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${runs}    msg=No planning run exists.
    RETURN    ${runs}[0]

The Newest Run Has Finished
    [Documentation]    Fail until the newest run has stopped running.
    ...
    ...    Polled rather than slept on: the solve has a thirty-second budget
    ...    but gives up sooner when the constraint is unsatisfiable, and a
    ...    fixed sleep would be either flaky or slow.
    ${run}=    Latest Run
    Should Not Be Equal    ${run}[status]    pending
    Should Not Be Equal    ${run}[status]    running

Remove This Run's Customer
    [Documentation]    Delete the customer and the accepted quote hanging off them.
    ...
    ...    Before the service is retired, and it is the step that matters: an
    ...    accepted quote on a gated service goes on failing every planning run
    ...    for as long as it exists, retired or not.
    ${headers}=    Manager Headers
    IF    '${QA_CUSTOMER_ID}' != '${EMPTY}'
        DELETE
        ...    ${API_URL}/api/v1/customers/${QA_CUSTOMER_ID}
        ...    headers=${headers}
        ...    expected_status=any
    END

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
