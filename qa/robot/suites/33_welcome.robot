*** Settings ***
Documentation    The public landing page, and the one control on it that changes meaning.
...
...              The page describes what the product does, and it is reachable
...              both signed in and signed out. So its session button cannot be
...              labelled from a role — it has to say what the visitor can do
...              next. Signed out it offers the way in; signed in it offers the
...              way out and stays put, because the signed-out application has
...              nowhere else to send them.
...
...              The routing assertions matter as much as the page. Introducing
...              a landing page means deciding what the *root* is, and the first
...              answer was wrong: everything unnamed fell to the welcome page,
...              which put a product tour in front of an operator whose session
...              had expired on ``/quotes`` and broke every suite that opens the
...              application and signs in. The rule is narrow on purpose — the
...              landing page is named, the sign-in form is the fallback — and
...              the two tests at the foot of this suite are what hold it there.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Root Is The Welcome Page
    [Documentation]    A visitor arriving cold is told what this is.
    [Tags]    smoke    welcome
    Go To    ${BASE_URL}
    Wait For Elements State    [data-testid="welcome-hero"]    visible

It Describes Every Feature Of The Application
    [Documentation]    The page's whole job, so the count is asserted rather than sampled.
    ...
    ...    A landing page that lists three of nine capabilities answers "does
    ...    this do my job?" with a maybe. The number is the contract.
    [Tags]    smoke    welcome
    ${cards}=    Get Element Count    [data-testid^="feature-"]
    Should Be Equal As Integers    ${cards}    9
    ...    msg=The welcome page no longer describes all nine features.
    Wait For Elements State    [data-testid="feature-quote"]    visible
    Wait For Elements State    [data-testid="feature-planning"]    visible
    Wait For Elements State    [data-testid="feature-notification"]    visible

It Says Who Each Part Is For
    [Documentation]    Three roles, because a reader places themselves before they read on.
    [Tags]    welcome
    Wait For Elements State    [data-testid="welcome-roles"]    visible
    ${roles}=    Get Element Count    [data-testid^="role-"]
    Should Be Equal As Integers    ${roles}    3

Signed Out It Offers The Way In
    [Documentation]    And says nothing about who is reading, because it does not know.
    [Tags]    smoke    welcome
    ${named}=    Get Element Count    [data-testid="welcome-signed-in-as"]
    Should Be Equal As Integers    ${named}    0
    ...    msg=The signed-out page claims to know who is reading it.
    Click    [data-testid="welcome-session-button"]
    Wait For Elements State    [data-testid="login-submit"]    visible

Signed In It Offers The Way Out And Names Them
    [Documentation]    The same button, the other meaning.
    ...
    ...    Reached by typing the address rather than by a link, which is the
    ...    honest test: the page sits outside the shell, so nothing in the
    ...    navigation points at it and a route that only worked on a soft
    ...    transition would look fine everywhere else.
    [Tags]    smoke    welcome
    Sign In As    ${MANAGER_EMAIL}
    Go To    ${BASE_URL}/welcome
    Wait For Elements State    [data-testid="welcome-signed-in-as"]    visible
    ${button}=    Get Text    [data-testid="welcome-session-button"]
    Should Not Be Empty    ${button}

Signing Out From It Comes Back To It
    [Documentation]    **Both halves, and the second is the one that was easy to miss.**
    ...
    ...    Ending the session without navigating would leave the signed-in
    ...    routes rendering for a session that no longer exists. Landing back
    ...    here is also the only sensible destination: the signed-out
    ...    application has no other page that means anything to somebody who
    ...    just chose to leave.
    [Tags]    smoke    welcome
    Click    [data-testid="welcome-session-button"]
    Wait For Elements State    [data-testid="welcome-hero"]    visible
    ${named}=    Get Element Count    [data-testid="welcome-signed-in-as"]
    Should Be Equal As Integers    ${named}    0
    ...    msg=The page still names a user after the session ended.
    ${session}=    Get Element Count    [data-testid="sign-out"]
    Should Be Equal As Integers    ${session}    0
    ...    msg=Signing out from the welcome page left the session open.

The Foot Of The Page Carries The Same Control
    [Documentation]    The page is long. A reader who reached the end should not scroll back.
    [Tags]    welcome
    Click    [data-testid="welcome-session-button-footer"]
    Wait For Elements State    [data-testid="login-submit"]    visible

A Stale Deep Link Still Reaches The Sign-In Form
    [Documentation]    **The regression this suite exists for.**
    ...
    ...    An expired session on a working screen is not a visitor to be
    ...    introduced to the product — it is somebody who wants their password
    ...    box. Only the root and ``/welcome`` are the landing page; everything
    ...    else falls to the form, exactly as it did before there was one.
    [Tags]    smoke    welcome    routing
    Go To    ${BASE_URL}/quotes
    Wait For Elements State    [data-testid="login-submit"]    visible
    ${hero}=    Get Element Count    [data-testid="welcome-hero"]
    Should Be Equal As Integers    ${hero}    0
    ...    msg=A stale deep link showed the product tour instead of the sign-in form.

The Sign-In Screen Is Still Reachable By Address
    [Documentation]    What ``Sign In As`` relies on now that the root is not the form.
    [Tags]    welcome    routing
    Go To    ${BASE_URL}/login
    Wait For Elements State    [data-testid="login-email"]    visible


*** Keywords ***
Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
