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
    ...    ``QA-DEVIS-20260806-085301-4821`` does not.
    ${stamp}=    Get Current Date    result_format=%Y%m%d-%H%M%S
    ${random}=    Generate Random String    4    [NUMBERS]
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

Notifications Of
    [Documentation]    Return an account's notifications.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/notifications    headers=${headers}    expected_status=200
    RETURN    ${response.json()}
