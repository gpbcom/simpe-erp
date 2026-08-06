*** Settings ***
Documentation    Routing, role guards, redirects and the unknown-route fallback.
...
...              Every one of these is reached by typing a URL rather than by
...              clicking, because that is the only way to exercise them. A
...              guard that works when the link is hidden but not when the
...              address is typed is a guard that does nothing.
...
...              These are *convenience* controls — the server refuses each of
...              these requests regardless — but a screen an assistant can reach
...              and that only shows them errors is a support ticket waiting to
...              be filed.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
An Unauthenticated Visitor Gets The Sign-In Card
    [Documentation]    Whatever address they typed.
    [Tags]    smoke    routing
    Go To    ${BASE_URL}/quotes
    Wait For Elements State    [data-testid="login-card"]    visible
    Go To    ${BASE_URL}/me/planning
    Wait For Elements State    [data-testid="login-card"]    visible

A Manager Lands On The Quote Screen
    [Documentation]    Their home is the work waiting for them.
    [Tags]    smoke    routing
    Sign In As    ${MANAGER_EMAIL}
    Go To    ${BASE_URL}/
    Wait For Elements State    [data-testid="quote-tabs"]    visible
    [Teardown]    Sign Out

An Assistant Lands On Their Planning
    [Documentation]    A different home for a different job.
    [Tags]    smoke    routing
    Sign In As    ${ASSISTANT_EMAIL}
    Go To    ${BASE_URL}/
    Wait For Elements State    [data-testid="planning-calendar"]    visible
    [Teardown]    Sign Out

An Assistant Typing A Manager URL Is Redirected Home
    [Documentation]    The guard, exercised the only way that proves it works.
    ...
    ...    **The test the role routing rests on.** Hiding the navigation entry
    ...    proves nothing: an assistant who bookmarks ``/hcas``, or follows a
    ...    link a colleague pasted, arrives by address. They must land
    ...    somewhere useful rather than on a screen full of 403s.
    [Tags]    smoke    routing    access
    Sign In As    ${ASSISTANT_EMAIL}
    FOR    ${forbidden}    IN    /quotes    /hcas    /map
        Go To    ${BASE_URL}${forbidden}
        Wait For Elements State    [data-testid="planning-calendar"]    visible
    END
    [Teardown]    Sign Out

An Unknown Route Falls Back To The Home Screen
    [Documentation]    Not a blank page, and not a browser error.
    [Tags]    routing
    Sign In As    ${MANAGER_EMAIL}
    Go To    ${BASE_URL}/there-is-no-such-screen
    Wait For Elements State    [data-testid="quote-tabs"]    visible
    [Teardown]    Sign Out

A Manager May Use The Self-Service Quote Screen
    [Documentation]    Authorship is an account property, not an assistant one.
    ...
    ...    ``/me/quotes`` is scoped by account, so a manager who writes a quote
    ...    has as much claim to "my quotes" as an assistant does. The two halves
    ...    of ``/me`` are deliberately scoped differently, and this is the
    ...    difference.
    [Tags]    routing    access
    Sign In As    ${MANAGER_EMAIL}
    Go To    ${BASE_URL}/me/quotes
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible
    [Teardown]    Sign Out

A Manager Has No Assistant Screens In The Navigation
    [Documentation]    An account bound to no assistant record hides them.
    ...
    ...    A manager has no ``hca_id``, so their own planning and customer
    ...    portfolio do not exist. Showing the entries and serving an empty list
    ...    would read as "you have no customers" rather than "this is not your
    ...    screen".
    [Tags]    routing    access
    Sign In As    ${MANAGER_EMAIL}
    ${planning}=    Get Element Count    [data-testid="nav--me-planning"]
    ${customers}=    Get Element Count    [data-testid="nav--me-customers"]
    Should Be Equal As Integers    ${planning}     0
    Should Be Equal As Integers    ${customers}    0
    [Teardown]    Sign Out

An Assistant Has No Manager Screens In The Navigation
    [Documentation]    The mirror image, for the other role.
    [Tags]    routing    access
    Sign In As    ${ASSISTANT_EMAIL}
    FOR    ${hidden}    IN    nav--quotes    nav--hcas    nav--map
        ${count}=    Get Element Count    [data-testid="${hidden}"]
        Should Be Equal As Integers    ${count}    0
    END
    [Teardown]    Sign Out

Both Roles Reach The Notification Centre
    [Documentation]    Everybody is notified about something.
    [Tags]    routing    access
    Sign In As    ${ASSISTANT_EMAIL}
    Go To    ${BASE_URL}/notifications
    Wait For Elements State    [data-testid="page-mark-all-read"]    visible
    Sign Out

    Sign In As    ${MANAGER_EMAIL}
    Go To    ${BASE_URL}/notifications
    Wait For Elements State    [data-testid="page-mark-all-read"]    visible
    [Teardown]    Sign Out

A Session Survives A Reload
    [Documentation]    The stored token is resolved on start-up.
    ...
    ...    Without this an operator is signed out by every refresh, which is the
    ...    first thing anybody does when a screen looks wrong.
    [Tags]    smoke    routing    auth
    Sign In As    ${MANAGER_EMAIL}
    Reload
    Wait For Elements State    [data-testid="current-user"]    visible
    [Teardown]    Sign Out

A Rejected Token Returns To The Sign-In Card
    [Documentation]    A credential the server no longer accepts is discarded.
    ...
    ...    A token that has stopped working is worse than none: every screen
    ...    fails with a different symptom instead of one clear sign-in page.
    ...    Simulated by corrupting the stored token, which is what an expired or
    ...    revoked one amounts to from the client's side.
    [Tags]    routing    auth
    Sign In As    ${MANAGER_EMAIL}
    LocalStorage Set Item    rt-erp.token    not-a-real-token
    Reload
    Wait For Elements State    [data-testid="login-card"]    visible
    ${token}=    LocalStorage Get Item    rt-erp.token
    Should Be Equal    ${token}    ${None}


*** Keywords ***
Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
