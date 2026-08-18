*** Settings ***
Documentation    Making an assistant a manager, from the screen they are already on.
...
...              What a manager may do is decided by their role, and there was
...              no way to change one. The API had ``POST /users/{id}/promote``
...              and nothing reached it.
...
...              **This suite edits a seeded account, which no other suite does,
...              so it puts it back.** The teardown demotes whoever was promoted
...              rather than trusting the test that promoted them to have got
...              that far: a run that fails mid-promotion still leaves an
...              assistant holding a manager's rights, and the next run would
...              find them already promoted and the button gone.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Workforce As An Administrator
Suite Teardown   Put Everybody Back
Test Teardown    Take A Screenshot On Failure


*** Variables ***
# The account this run promoted, so the teardown can demote it. Recorded before
# the promotion is confirmed, not after it is verified.
${PROMOTED_ACCOUNT_ID}      ${EMPTY}


*** Test Cases ***
The Workforce Shows What Each Assistant May Do
    [Documentation]    A role beside the person, not on a separate accounts list.
    [Tags]    smoke    promotion
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    # Waited for, not counted straight away. The roles come from a *second*
    # request — the accounts list — so the grid is on screen before they are,
    # and counting immediately reports zero on a fast machine and one on a slow
    # one.
    Wait For Elements State    css=[data-testid^="role-"] >> nth=0    visible
    ${roles}=    Get Element Count    css=[data-testid^="role-"]
    Should Be True    ${roles} > 0    msg=No role is shown for any assistant.

An Administrator Can Promote An Assistant To Manager
    [Documentation]    The whole point, asserted on the stored role.
    ...
    ...    Read back through the API rather than off the chip: the chip proves
    ...    the browser believes it, and what decides whether they can validate a
    ...    quote tomorrow is what the server stored.
    [Tags]    smoke    promotion
    ${account}=    An Assistant Account
    Set Suite Variable    ${PROMOTED_ACCOUNT_ID}    ${account}[id]

    Wait For Elements State    [data-testid="promote-${account}[hca_id]"]    visible
    Click    [data-testid="promote-${account}[hca_id]"]
    Wait For Elements State    [data-testid="promote-dialog"]    visible
    Click    [data-testid="promote-confirm"]
    Wait For Elements State    [data-testid="promote-dialog"]    detached

    Wait Until Keyword Succeeds    10s    1s
    ...    Account Should Hold The Role    ${account}[id]    manager

The Promoted Assistant Is No Longer Offered For Promotion
    [Documentation]    The button belongs to assistants, not to everybody.
    ...
    ...    A manager offered "promote to manager" is an operator wondering
    ...    whether the first click worked.
    [Tags]    promotion
    Skip If    '${PROMOTED_ACCOUNT_ID}' == '${EMPTY}'
    ...    Nobody was promoted, so there is nothing to check.
    Reload
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    ${account}=    Account With Id    ${PROMOTED_ACCOUNT_ID}
    ${buttons}=    Get Element Count    [data-testid="promote-${account}[hca_id]"]
    Should Be Equal As Integers    ${buttons}    0

A Manager Sees The Workforce Without The Role Column
    [Documentation]    The accounts list is an administrator's, and this says so.
    ...
    ...    A manager cannot read accounts, so a role column would show "no
    ...    account" against every assistant — which states a fact about the
    ...    agency when it is really one about the reader. The column is absent
    ...    instead.
    [Tags]    promotion    access
    Sign Out
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    ${roles}=    Get Element Count    css=[data-testid^="role-"]
    Should Be Equal As Integers    ${roles}    0
    [Teardown]    Return To The Administrator


*** Keywords ***
Open The Workforce As An Administrator
    [Documentation]    Sign in as an administrator and open the workforce.
    Open The Application Without Coverage
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible

An Assistant Account
    [Documentation]    Return an account that still holds the assistant role.
    ${accounts}=    Accounts
    ${matching}=    Evaluate
    ...    [u for u in $accounts if u["role"]=="hca" and u["hca_id"]]
    Should Not Be Empty    ${matching}
    ...    msg=No assistant account is left to promote; was the seeder run?
    RETURN    ${matching}[0]

Account With Id
    [Documentation]    Return one stored account.
    [Arguments]    ${account_id}
    ${accounts}=    Accounts
    ${matching}=    Evaluate
    ...    [u for u in $accounts if u["id"]=="""${account_id}"""]
    Should Not Be Empty    ${matching}    msg=Account ${account_id} is gone.
    RETURN    ${matching}[0]

Accounts
    [Documentation]    Return every stored account.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/users
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    RETURN    ${response.json()}

Account Should Hold The Role
    [Documentation]    Assert an account's stored role.
    [Arguments]    ${account_id}    ${expected}
    ${account}=    Account With Id    ${account_id}
    Should Be Equal    ${account}[role]    ${expected}

Return To The Administrator
    [Documentation]    Leave the suite signed in as it started.
    Take A Screenshot On Failure
    Sign Out
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible

Put Everybody Back
    [Documentation]    Demote whoever this run promoted, then close the browser.
    ...
    ...    Through the API, so it runs whatever the browser is showing. Without
    ...    it the seeded workforce gains a manager per run, and the second run
    ...    finds one fewer assistant to promote than the first.
    ${status}    ${error}=    Run Keyword And Ignore Error    Demote The Promoted Account
    Close The Application Without Coverage
    IF    '${status}' != 'PASS'
        Fail    The promoted assistant was left a manager: ${error}
    END

Demote The Promoted Account
    [Documentation]    Put the promoted account back to the assistant role.
    IF    '${PROMOTED_ACCOUNT_ID}' == '${EMPTY}'
        Log    This run promoted nobody. Nothing to undo.
        RETURN
    END
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary    role=hca
    POST
    ...    ${API_URL}/api/v1/users/${PROMOTED_ACCOUNT_ID}/promote
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
