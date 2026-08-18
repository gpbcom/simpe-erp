*** Settings ***
Documentation    Founding an agency from the sign-in card, and becoming its administrator.
...
...              The one screen somebody with no account can reach and act on.
...              Everything else in this campaign starts signed in. This starts
...              from nothing and ends with a session.
...
...              **Idempotent by construction, and it has to work harder at it
...              than the other suites do.** The others create quotes and delete
...              them. This creates an *agency and an account*, which are what
...              every other record hangs off. The suffix keeps two runs from
...              colliding, and the teardown removes the account first and then
...              the agency — in that order, because an agency somebody still
...              belongs to refuses to be deleted.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application Without Coverage
Suite Teardown   Remove Whatever This Run Founded
Test Setup       Start From The Sign-In Card
Test Teardown    Take A Screenshot On Failure


*** Variables ***
# Recorded by the test that founds the agency, and read by the teardown.
#
# The **name and address** are stored, not the identifiers, and they are
# stored *before* the form is submitted rather than after the agency is read
# back. A test that fails between the submit and the read-back has still
# created an agency, and a teardown keyed on an identifier it never got to
# learn cannot remove it — which is exactly how this suite leaked an agency
# the first time it was run. Resolving by name at teardown covers the whole
# window.
${FOUNDED_COMPANY_NAME}     ${EMPTY}
${FOUNDER_EMAIL}            ${EMPTY}
${FOUNDER_PASSWORD}         qa-founder-password-2026


*** Test Cases ***
The Sign-In Card Offers To Found An Agency
    [Documentation]    The route is advertised where somebody with no account is.
    ...
    ...    The link is the only place it is advertised, so its absence is what a
    ...    deployment that has not opted in looks like from the outside.
    [Tags]    smoke    registration
    Wait For Elements State    [data-testid="login-register-company"]    visible
    Click                      [data-testid="login-register-company"]
    Wait For Elements State    [data-testid="register-company-card"]     visible

The Form Comes Back To The Sign-In Card
    [Documentation]    Somebody who opened it by mistake is not trapped.
    [Tags]    registration
    Open The Registration Form
    Click                      [data-testid="register-company-cancel"]
    Wait For Elements State    [data-testid="login-card"]    visible

Founding An Agency Signs Its Founder In As Administrator
    [Documentation]    The whole point: no account, then an agency and a session.
    ...
    ...    Asserted on the *stored* role as well as on the screen. A manager
    ...    screen appearing proves the client thinks the founder is privileged;
    ...    reading the account back proves the server does, which is the half
    ...    that matters.
    [Tags]    smoke    registration
    ${suffix}=    Unique Suffix
    ${name}=      Set Variable    QA Agence ${suffix}
    ${email}=     Set Variable    qa-founder-${suffix}@simple-erp.fr
    # Before the form is submitted, so the teardown can find whatever this
    # test creates even if it fails on the very next line.
    Set Suite Variable    ${FOUNDED_COMPANY_NAME}    ${name}
    Set Suite Variable    ${FOUNDER_EMAIL}           ${email}

    Open The Registration Form
    Fill Text    [data-testid="register-company-name"]      ${name}
    Fill Text    [data-testid="register-company-founder"]   Camille QA
    Fill Text    [data-testid="register-company-email"]     ${email}
    Fill Text    [data-testid="register-company-password"]  ${FOUNDER_PASSWORD}
    Click        [data-testid="register-company-submit"]

    # Signed in without going back to the sign-in card: the page follows the
    # registration with a login using the password just chosen.
    Wait For Elements State    [data-testid="current-user"]    visible
    # An administrator's home is the work queue, not an assistant's planning.
    Wait For Elements State    [data-testid="quote-tabs"]      visible

    ${agency}=    Agency Named    ${name}
    Should Not Be Equal    ${agency}    ${None}    msg=The agency was not stored.

    ${account}=    Account Signed In As    ${email}
    Should Be Equal    ${account}[role]          admin
    Should Be Equal    ${account}[company_id]    ${agency}[id]

A Taken Name Is Refused Rather Than Silently Accepted
    [Documentation]    Two agencies trading under one name cannot be told apart.
    ...
    ...    Uses the seeded agency's name, which is always there and which this
    ...    suite never edits — so the refusal is exercised without creating a
    ...    second fixture to clean up.
    [Tags]    registration
    ${suffix}=    Unique Suffix
    Open The Registration Form
    Fill Text    [data-testid="register-company-name"]      ${SEEDED_COMPANY_NAME}
    Fill Text    [data-testid="register-company-founder"]   Clash QA
    Fill Text    [data-testid="register-company-email"]     qa-clash-${suffix}@simple-erp.fr
    Fill Text    [data-testid="register-company-password"]  ${FOUNDER_PASSWORD}
    Click        [data-testid="register-company-submit"]

    Wait For Elements State    [data-testid="register-company-error"]    visible
    # Still on the form, not signed in: a refusal must not look like a success.
    Wait For Elements State    [data-testid="register-company-card"]     visible

A Taken Address Is Refused The Same Way
    [Documentation]    The founder's address is a credential. It cannot be reused.
    [Tags]    registration
    ${suffix}=    Unique Suffix
    Open The Registration Form
    Fill Text    [data-testid="register-company-name"]      QA Agence ${suffix}
    Fill Text    [data-testid="register-company-founder"]   Clash QA
    Fill Text    [data-testid="register-company-email"]     ${ADMIN_EMAIL}
    Fill Text    [data-testid="register-company-password"]  ${FOUNDER_PASSWORD}
    Click        [data-testid="register-company-submit"]

    Wait For Elements State    [data-testid="register-company-error"]    visible


*** Keywords ***
Open The Registration Form
    [Documentation]    Get from the sign-in card to the agency form.
    Wait For Elements State    [data-testid="login-register-company"]    visible
    Click                      [data-testid="login-register-company"]
    Wait For Elements State    [data-testid="register-company-card"]     visible

Start From The Sign-In Card
    [Documentation]    Begin every test signed out, whatever the last one left.
    ...
    ...    One test here ends signed in as a founder. Without this the next
    ...    would look for a sign-in card that is not on screen, and one real
    ...    failure would become several.
    Go To    ${BASE_URL}
    # One wait, for whichever of the two the boot lands on. Waiting for the
    # signed-in case alone and swallowing the timeout gets the same answer, but
    # spends five seconds and writes a TimeoutError into the log of a run in
    # which nothing failed.
    Wait For Elements State
    ...    css=[data-testid="sign-out"], [data-testid="login-submit"]    visible
    ${signed_in}=    Get Element Count    [data-testid="sign-out"]
    IF    ${signed_in} > 0
        Sign Out
    END
    Wait For Elements State    [data-testid="login-submit"]    visible

Account Named
    [Documentation]    Return the stored account with an address, or ``None``.
    ...
    ...    The tolerant sibling of ``Account Signed In As``: the teardown has
    ...    to cope with the account never having been created.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/users
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [u for u in $response.json() if u["""email"""]=="""${email}"""]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

Account Signed In As
    [Documentation]    Read an account back through the API.
    ...
    ...    Read as the seeded administrator rather than as the founder, so the
    ...    assertion does not depend on the very session it is checking.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/users
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [u for u in $response.json() if u["email"]=="""${email}"""]
    Should Not Be Empty    ${matching}    msg=No account was stored for ${email}.
    RETURN    ${matching}[0]

Remove Whatever This Run Founded
    [Documentation]    Put the stack back as it was found, then close the browser.
    ...
    ...    The browser closes either way, but a cleanup that could not finish
    ...    fails the suite rather than passing quietly: an agency left behind
    ...    breaks the *next* run, one further from its cause than this one.
    ${status}    ${error}=    Run Keyword And Ignore Error    Remove The Founded Agency
    Close The Application Without Coverage
    IF    '${status}' != 'PASS'
        Fail    The agency this run founded was left behind: ${error}
    END

Remove The Founded Agency
    [Documentation]    Delete the founder and the agency, whatever reached the store.
    ...
    ...    Resolved by name and address rather than by remembered identifiers.
    ...    Either half may exist without the other — the agency is written
    ...    first, so a failure between the two leaves an agency and no
    ...    account — and both are looked up independently so whichever
    ...    landed is removed.
    IF    '${FOUNDED_COMPANY_NAME}' == '${EMPTY}'
        Log    This run founded no agency. Nothing to remove.
        RETURN
    END
    ${agency}=    Agency Named    ${FOUNDED_COMPANY_NAME}
    ${account}=   Account Named   ${FOUNDER_EMAIL}
    ${company_id}=    Set Variable If    ${agency}    ${agency}[id]     ${EMPTY}
    ${admin_id}=      Set Variable If    ${account}   ${account}[id]    ${EMPTY}
    Remove The Agency Founded By This Run    ${company_id}    ${admin_id}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
