*** Settings ***
Documentation    Setting up and tearing down through the API, never the UI.
...
...              A suite that prepares itself by clicking is a suite that
...              cannot clean up when it fails half-way through — the browser
...              is already on an error page, and the fixture it made is left
...              behind to break the next run. Every fixture here is created
...              and removed over HTTP, which works regardless of what the
...              browser is doing.

Library          RequestsLibrary
Library          Collections
Library          String
Library          DateTime
Resource         config.resource


*** Keywords ***
Sign In Through The API
    [Documentation]    Return a bearer token for an account.
    ...    Built with Create Dictionary rather than written inline. An inline
    ...    ``json={"email": "..."}`` reaches RequestsLibrary as a *string*, and
    ...    a string is sent as a JSON string rather than a JSON object — which
    ...    the API answers 422, "Input should be a valid dictionary", for every
    ...    request the campaign makes.
    [Arguments]    ${email}    ${password}=${SEED_PASSWORD}
    ${body}=    Create Dictionary    email=${email}    password=${password}
    ${response}=    POST
    ...    ${API_URL}/api/v1/auth/login
    ...    json=${body}
    ...    expected_status=200
    RETURN    ${response.json()}[access_token]

Authorisation Header
    [Documentation]    Return the bearer header for a token.
    [Arguments]    ${token}
    ${headers}=    Create Dictionary    Authorization=Bearer ${token}
    RETURN    ${headers}

Unique Suffix
    [Documentation]    Return a suffix no other run will produce.
    ...
    ...    This is what lets the campaign run twice against the same stack. A
    ...    fixture named ``QA-DEVIS`` collides on the second run; one named
    ...    ``QA-DEVIS-20260806-085301-4821x`` does not.
    ...
    ...    **The random part carries the uniqueness, not the timestamp.** The
    ...    stamp has one-second granularity, so it distinguishes nothing between
    ...    two workers that start a fixture in the same second — which is the
    ...    normal case once the campaign is sharded across parallel runs. Four
    ...    digits gave a collision every ten thousand draws per pair, and a
    ...    collision here presents as a mysterious 409 in an unrelated suite.
    ...
    ...    Eight alphanumerics instead: ~2.8e12 combinations, and letters as
    ...    well as digits so a suffix cannot be mistaken for a reference number.
    ...    The stamp stays because it is what makes a leftover fixture readable
    ...    when one does survive a failed teardown.
    ${stamp}=    Get Current Date    result_format=%Y%m%d-%H%M%S
    ${random}=    Generate Random String    8    [LETTERS][NUMBERS]
    RETURN    ${stamp}-${random}

Create A Draft Quote As
    [Documentation]    Write a quote through the API and return it.
    ...
    ...    Created as the *assistant*, so the quote is theirs and the
    ...    submission path can be exercised. A quote a manager wrote would
    ...    skip the validation step entirely, which is the thing under test.
    [Arguments]    ${email}    ${customer_id}    ${type_id}    ${suffix}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${service_date}=    Get Current Date    increment=14 days    result_format=%Y-%m-%d
    ${body}=    Catenate    SEPARATOR=
    ...    {"reference": "QA-${suffix}",
    ...    "customer_id": "${customer_id}",
    ...    "lines": [{"name": "Aide a la toilette",
    ...    "intervention_type_id": "${type_id}",
    ...    "service_category": "necessity",
    ...    "service_date": "${service_date}",
    ...    "earliest_start": "09:00:00",
    ...    "latest_end": "12:00:00",
    ...    "duration_minutes": 60}]}
    ${response}=    POST
    ...    ${API_URL}/api/v1/me/quotes
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=201
    RETURN    ${response.json()}

Create A Draft Quote As A Manager
    [Documentation]    Write a quote a manager owns, and return it.
    ...
    ...    The counterpart to ``Create A Draft Quote As``: this one is authored
    ...    by a manager, so it is *not* the assistant's. It is what the scoping
    ...    tests need — a quote that exists, is a draft, and belongs to
    ...    somebody else. Without it, "the assistant cannot edit a foreign
    ...    quote" could pass because the quote was missing rather than because
    ...    the ownership check ran.
    [Arguments]    ${customer_id}    ${type_id}    ${suffix}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${service_date}=    Get Current Date    increment=14 days    result_format=%Y-%m-%d
    ${body}=    Catenate    SEPARATOR=
    ...    {"reference": "QA-${suffix}",
    ...    "customer_id": "${customer_id}",
    ...    "lines": [{"name": "Aide a la toilette",
    ...    "intervention_type_id": "${type_id}",
    ...    "service_category": "necessity",
    ...    "service_date": "${service_date}",
    ...    "earliest_start": "09:00:00",
    ...    "latest_end": "12:00:00",
    ...    "duration_minutes": 60}]}
    ${response}=    POST
    ...    ${API_URL}/api/v1/quotes
    ...    data=${body}
    ...    headers=${{ {**$headers, "Content-Type": "application/json"} }}
    ...    expected_status=201
    RETURN    ${response.json()}

Quote Read By A Manager
    [Documentation]    Return a quote as the server currently holds it.
    ...
    ...    Read back through the API rather than trusted from the screen. What
    ...    the editor shows after a save is what the client re-fetched; what
    ...    the customer is billed from is this.
    [Arguments]    ${quote_id}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes/${quote_id}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Submit Quote Through The API
    [Documentation]    Put a quote into the validation queue.
    [Arguments]    ${email}    ${quote_id}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    POST
    ...    ${API_URL}/api/v1/me/quotes/${quote_id}/submit
    ...    headers=${headers}
    ...    expected_status=200

First Customer Of
    [Documentation]    Return the identifier of an assistant's first customer.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/customers    headers=${headers}    expected_status=200
    ${customers}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${customers}
    ...    msg=The seeded assistant has no customers; was the seeder run?
    RETURN    ${customers}[0][id]

Family Name Of The First Customer Of
    [Documentation]    Return the surname of an assistant's first customer.

    ...    Read rather than written down. Which customers an assistant holds
    ...    follows from the quotes the seeder happened to attribute to them, so
    ...    a name spelled out in a suite is a name that goes stale the first
    ...    time the seeded spread changes.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/customers    headers=${headers}    expected_status=200
    ${customers}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${customers}
    ...    msg=The seeded assistant has no customers; was the seeder run?
    RETURN    ${customers}[0][last_name]

First Intervention Type
    [Documentation]    Return the identifier of the first catalog entry.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/intervention-types
    ...    headers=${headers}
    ...    expected_status=200
    ${types}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${types}    msg=The catalog is empty; was the seeder run?
    RETURN    ${types}[0][id]

Quote Status Should Become
    [Documentation]    Poll a quote until it reaches a status, or give up.
    ...
    ...    Polled rather than asserted once, because the status changes after a
    ...    broker round trip. Asserting immediately would fail on a slow
    ...    machine and pass on a fast one, which is the definition of a flaky
    ...    test.
    [Arguments]    ${quote_id}    ${expected}
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    1s
    ...    Quote Status Is    ${quote_id}    ${expected}    ${headers}

Quote Status Is
    [Documentation]    Assert a quote's current status.
    [Arguments]    ${quote_id}    ${expected}    ${headers}
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes/${quote_id}    headers=${headers}
    Should Be Equal    ${response.json()}[status]    ${expected}

Remove The Quotes Created By This Run
    [Documentation]    Delete a run's own quotes, and say so if one survives.
    ...
    ...    [Arguments] is a list of identifiers this run created — never a
    ...    pattern. A teardown that deleted by reference prefix would take a
    ...    concurrent run's fixtures with it.
    ...
    ...    A quote that is already gone is not a failure: a test may have
    ...    deleted it itself, and the same run is entitled to be torn down
    ...    twice. Anything else is reported. Swallowing it would leave the
    ...    fixture behind and break the *next* run instead of this one, which
    ...    is the hardest kind of failure to trace back to its cause.
    [Arguments]    @{quote_ids}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    @{survivors}=    Create List
    FOR    ${quote_id}    IN    @{quote_ids}
        ${status}    ${result}=    Run Keyword And Ignore Error
        ...    DELETE
        ...    ${API_URL}/api/v1/quotes/${quote_id}
        ...    headers=${headers}
        ...    expected_status=any
        IF    '${status}' != 'PASS'
            Append To List    ${survivors}    ${quote_id} (${result})
        ELSE IF    ${result.status_code} not in [200, 204, 404]
            Append To List    ${survivors}    ${quote_id} (HTTP ${result.status_code})
        END
    END
    Should Be Empty    ${survivors}
    ...    msg=Quotes this run created could not be deleted, so the stack is no longer as it was found: @{survivors}

Clear The Mail Catcher
    [Documentation]    Empty Mailpit so a test asserts only on its own mail.
    Run Keyword And Ignore Error    DELETE    ${MAILPIT_URL}/api/v1/messages

Notification Should Have Reached
    [Documentation]    Assert an account's queue mentions a phrase.
    ...
    ...    Read over the API rather than off the screen, so it can be waited on
    ...    without a browser and without a popover being open.
    [Arguments]    ${email}    ${phrase}
    ${notifications}=    Notifications Of    ${email}
    ${titles}=    Evaluate    [n["title"] for n in $notifications]
    ${joined}=    Catenate    @{titles}
    Should Contain    ${joined}    ${phrase}

Notifications Of
    [Documentation]    Return an account's notifications.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/notifications    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Remove The Agency Founded By This Run
    [Documentation]    Delete an agency and its founder, in that order.
    ...
    ...    The order is not a preference: an agency with anybody still attached
    ...    answers 409, because every account names the agency it belongs to
    ...    and removing one underneath the other would leave a row nothing can
    ...    rebuild. The founder goes first, then the agency they founded.
    ...
    ...    Absence is tolerated — a test may have removed one half already —
    ...    but anything else is reported. A cleanup that fails quietly leaves
    ...    an agency behind and breaks the *next* run, which is the failure
    ...    this campaign's idempotency rule exists to prevent.
    [Arguments]    ${company_id}    ${administrator_id}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    @{survivors}=    Create List
    IF    '${administrator_id}' != '${EMPTY}'
        ${account}=    DELETE
        ...    ${API_URL}/api/v1/users/${administrator_id}
        ...    headers=${headers}
        ...    expected_status=any
        IF    ${account.status_code} not in [204, 404]
            Append To List    ${survivors}    account (HTTP ${account.status_code})
        END
    END
    IF    '${company_id}' != '${EMPTY}'
        ${agency}=    DELETE
        ...    ${API_URL}/api/v1/companies/${company_id}
        ...    headers=${headers}
        ...    expected_status=any
        IF    ${agency.status_code} not in [204, 404]
            Append To List    ${survivors}    agency (HTTP ${agency.status_code})
        END
    END
    Should Be Empty    ${survivors}
    ...    msg=The agency this run founded could not be removed: @{survivors}

Agency Named
    [Documentation]    Return the stored agency with a name, or ``None``.
    ...
    ...    The page size goes in ``params`` rather than in the URL. Robot
    ...    reads any ``name=value`` token as a *named argument*, so a query
    ...    string written inline is swallowed as one and the keyword is
    ...    called with no URL at all.
    [Arguments]    ${name}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/companies
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [c for c in $response.json() if c["name"]=="""${name}"""]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

Ensure A Planning Has Been Computed
    [Documentation]    Compute a planning if the window has no visits in it.
    ...
    ...    **Three suites read a planning they do not create.** The calendar
    ...    (08), the map (09) and the team planning (17) all assert on visits
    ...    that only exist once suite 19 has pressed *compute*. The seeder
    ...    writes quotes, not interventions, so on a virgin database there is
    ...    nothing to draw.
    ...
    ...    Two of them already degrade gracefully — 08 and 17 carry ``Skip If``
    ...    on an empty window — but 09 asserts ``${pins} > 0`` four times with
    ...    no guard at all, so it simply fails. That is latent today and only
    ...    hidden because a long-lived stack has always already had a planning
    ...    computed into it.
    ...
    ...    **Suite order cannot fix this.** Robot runs a directory's suites in
    ...    *name* order, so 08, 09 and 17 sort before 19 under every possible
    ...    arrangement, sharded or not. The precondition has to be asked for.
    ...
    ...    Keyed on *interventions in the window*, never on the status of the
    ...    newest run: suite 28 deliberately leaves a FAILED run at the head of
    ...    the list, and a status check would answer "no planning" for a stack
    ...    that has a perfectly good one — then pay a thirty-second solve to
    ...    prove itself wrong.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${monday}=    The Monday Of The Planned Week
    ${sunday}=    Add Time To Date    ${monday}    6 days    result_format=%Y-%m-%d
    ${params}=    Create Dictionary    period_start=${monday}    period_end=${sunday}
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/hcas
    ...    params=${params}    headers=${headers}    expected_status=200
    ${visits}=    Evaluate
    ...    sum(len(p["interventions"]) for p in $response.json())
    IF    ${visits} > 0
        Log    The window already holds ${visits} visit(s).    console=${True}
        RETURN
    END
    Log    No visit in the window; computing a planning first.    console=${True}
    POST
    ...    ${API_URL}/api/v1/planning/runs
    ...    params=${params}    headers=${headers}    expected_status=202
    Wait Until Keyword Succeeds    90s    3s    A Planning Covers The Window

A Planning Covers The Window
    [Documentation]    Fail until the planned week holds at least one visit.
    ...
    ...    Asserted on the *result* rather than on the run's status, for the
    ...    reason given in ``Ensure A Planning Has Been Computed``: another
    ...    suite's failed run may be newer than ours.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${monday}=    The Monday Of The Planned Week
    ${sunday}=    Add Time To Date    ${monday}    6 days    result_format=%Y-%m-%d
    ${params}=    Create Dictionary    period_start=${monday}    period_end=${sunday}
    ${response}=    GET
    ...    ${API_URL}/api/v1/planning/hcas
    ...    params=${params}    headers=${headers}    expected_status=200
    ${visits}=    Evaluate
    ...    sum(len(p["interventions"]) for p in $response.json())
    Should Be True    ${visits} > 0    msg=The planning run placed nothing.

The Monday Of The Planned Week
    [Documentation]    Return the Monday the seeder plans its work into.
    ...
    ...    Computed the same way the seeder computes it rather than written
    ...    down, so the window follows the seeded data instead of going stale
    ...    the day after it was typed. Suite 19 has its own copy of this for
    ...    historical reasons; this is the one the shared precondition uses.
    ${today}=      Get Current Date    result_format=%Y-%m-%d
    ${weekday}=    Convert Date    ${today}    result_format=%w
    ${ahead}=      Evaluate    7 - int(${weekday}) if int(${weekday}) > 0 else 1
    ${monday}=     Add Time To Date    ${today}    ${ahead} days
    ...    result_format=%Y-%m-%d
    RETURN    ${monday}
