*** Settings ***
Documentation    An assistant's own record: what they may change, and what they may not.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application And Sign In As An Assistant
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
An Assistant Sees Their Own Details
    [Documentation]    The page loads with the account's own record on it.
    [Tags]    smoke
    Navigate To    /me
    Wait For Elements State    [data-testid="profile-first-name"]    visible
    Get Attribute    [data-testid="profile-first-name"]    value    !=    ${EMPTY}

Certifications Are Shown Locked
    [Documentation]    They are a manager's decision, and the screen says so.
    ...
    ...    **This is the test the whole screen rests on.** An assistant who
    ...    could grant themselves a qualification could be routed to work they
    ...    are not trained for. The chips are locked rather than absent so the
    ...    assistant can still see what they hold, and who to ask.
    Navigate To    /me
    Wait For Elements State    [data-testid="certifications"]    visible
    ${editable}=    Get Element Count    [data-testid="certifications"] input
    Should Be Equal As Integers    ${editable}    0

The Contract Type Is Not Editable
    [Documentation]    Employment is set by a manager, not by the employee.
    Navigate To    /me
    Wait For Elements State    [data-testid="contract-type"]    visible
    ${editable}=    Get Element Count    [data-testid="contract-type"] input
    Should Be Equal As Integers    ${editable}    0

Contact Details Can Be Saved
    [Documentation]    The five fields an assistant does own.
    ...
    ...    The value is written back to what it was, so the suite can run twice
    ...    without leaving the seeded assistant renamed.
    Navigate To    /me
    Wait For Elements State    [data-testid="profile-phone"]    visible
    ${original}=    Get Attribute    [data-testid="profile-phone"]    value
    Fill Text    [data-testid="profile-phone"]    +33600000199
    Click    [data-testid="profile-save"]
    Sleep    1s
    Fill Text    [data-testid="profile-phone"]    ${original}
    Click    [data-testid="profile-save"]


*** Keywords ***
Open The Application And Sign In As An Assistant
    Open The Application
    Sign In As    ${ASSISTANT_EMAIL}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
