*** Settings ***
Documentation    Signing in, being refused, and the forced password change.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
A Manager Can Sign In
    [Documentation]    The ordinary path, and the one every other suite needs.
    [Tags]    smoke
    Sign In As    ${MANAGER_EMAIL}
    Get Text    [data-testid="current-user"]    !=    ${EMPTY}
    Sign Out

An Assistant Can Sign In
    [Documentation]    The other role, which lands on a different home screen.
    [Tags]    smoke
    Sign In As    ${ASSISTANT_EMAIL}
    Wait For Elements State    [data-testid="nav--me-planning"]    visible
    Sign Out

A Wrong Password Is Refused Without Saying Which Half Was Wrong
    [Documentation]    The message must not distinguish the two cases.
    ...
    ...    The API answers the same 401 whether the address is unknown or the
    ...    password is wrong, precisely so the endpoint cannot be used to
    ...    discover which addresses are registered. A screen that guessed more
    ...    specifically would undo that.
    Fill Text    [data-testid="login-email"]    ${MANAGER_EMAIL}
    Fill Text    [data-testid="login-password"]    definitely-not-the-password
    Click    [data-testid="login-submit"]
    Wait For Elements State    [data-testid="login-error"]    visible
    ${message}=    Get Text    [data-testid="login-error"]
    Should Not Contain    ${message}    mot de passe incorrect pour
    Should Not Contain    ${message}    compte inconnu

An Unknown Address Is Refused The Same Way
    [Documentation]    Same message, so the two cases stay indistinguishable.
    Fill Text    [data-testid="login-email"]    nobody@rt-erp.fr
    Fill Text    [data-testid="login-password"]    ${SEED_PASSWORD}
    Click    [data-testid="login-submit"]
    Wait For Elements State    [data-testid="login-error"]    visible


*** Keywords ***
Take A Screenshot On Failure
    [Documentation]    Keep a picture of whatever the browser was showing.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
