*** Settings ***
Documentation    The language a quote is emailed in, and what the document says.
...
...              The interface has offered French and English since it existed,
...              but the choice lived in the browser's ``localStorage`` and
...              never reached the server. That was enough while it only decided
...              what was on screen. It stopped being enough once the quotes
...              emailed to customers had to come out in it: those are built by
...              the planning-completed webhook, which runs in the background
...              with no browser attached and no header to read.
...
...              So the preference moved onto the account. These tests walk it
...              from the toggle in the top bar to the stored column, and back
...              out again — because a switch that changes the screen and not
...              the account looks identical to one that works, right up until
...              a customer receives a document in the wrong language.
...
...              **Idempotent by construction.** The language it changes is the
...              signed-in account's own, snapshotted before anything runs and
...              written back in a teardown that fires even when the test that
...              changed it failed.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Snapshot The Language And Open
Suite Teardown   Restore The Language And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${ORIGINAL_LANGUAGE}    ${EMPTY}


*** Test Cases ***
The Account Publishes The Language It Reads
    [Documentation]    The preference is server state, not only browser state.
    ...
    ...    Asserted on the API rather than on the screen. A field the interface
    ...    holds and the server does not is exactly the state this feature
    ...    exists to remove.
    [Tags]    smoke    i18n    quote-language
    ${account}=    Account As Stored
    Dictionary Should Contain Key    ${account}    language
    ...    msg=The account does not publish a language at all.
    Should Match Regexp    ${account}[language]    ^(fr|en)$

Switching The Language Stores It On The Account
    [Documentation]    **The switch this feature turns on.**
    ...
    ...    Before this, the toggle wrote ``localStorage`` and stopped. The
    ...    quotes went on being generated in French whatever the operator had
    ...    chosen, and nothing on screen said so.
    [Tags]    smoke    i18n    quote-language
    Sign In As    ${ADMIN_EMAIL}
    Switch Language To    en
    Wait For Elements State    text=Assistants    visible

    Wait Until Keyword Succeeds    10s    1s    Stored Language Should Be    en
    [Teardown]    Restore The Language And Sign Out

The Stored Language Is Adopted On Sign-In
    [Documentation]    A colleague's laptop must not decide your documents.
    ...
    ...    The screen and the emailed document have to agree. Signing in on a
    ...    machine last used in French, with English stored, used to leave the
    ...    interface French while every quote went out in English — two answers
    ...    to one question, and only one of them visible.
    [Tags]    smoke    i18n    quote-language
    Set The Stored Language To    en
    Sign In As    ${ADMIN_EMAIL}
    Wait For Elements State    text=Assistants    visible
    ...    message=The interface did not adopt the account's stored English.

    ${remembered}=    LocalStorage Get Item    simple-erp.language
    Should Be Equal    ${remembered}    en
    ...    msg=The adopted language was applied but not remembered.
    [Teardown]    Restore The Language And Sign Out

Editing The Account Does Not Reset The Language
    [Documentation]    The payload replaces the whole account, so it carries it.
    ...
    ...    A screen that omitted the field would silently put the holder back
    ...    to French every time they corrected a typo in their own name — and
    ...    the only symptom would be a customer's quote arriving in the wrong
    ...    language a fortnight later.
    [Tags]    i18n    quote-language
    Set The Stored Language To    en
    Sign In As    ${ADMIN_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="account-full-name"]    visible
    ${name}=    Get Property    [data-testid="account-full-name"]    value
    Fill Text    [data-testid="account-full-name"]    ${name} QA
    Click    [data-testid="save-account"]
    Wait For Elements State    [data-testid="account-saved"]    visible

    Stored Language Should Be    en
    [Teardown]    Restore The Name And Language Then Sign Out    ${name}

The Server Refuses A Language It Does Not Speak
    [Documentation]    A preference silently ignored is worse than one refused.
    ...
    ...    Sent by hand: the screen offers two buttons, so it can only ever
    ...    send a code the server knows. The guard is for everything else.
    [Tags]    smoke    i18n    quote-language    access
    ${account}=    Account As Stored
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    full_name=${account}[full_name]
    ...    email=${account}[email]
    ...    language=de
    PATCH
    ...    ${API_URL}/api/v1/me/account
    ...    json=${body}    headers=${headers}    expected_status=422

A Refused Language Leaves The Stored One Alone
    [Documentation]    The write is refused, not half-applied.
    [Tags]    i18n    quote-language
    Set The Stored Language To    fr
    ${account}=    Account As Stored
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    full_name=${account}[full_name]
    ...    email=${account}[email]
    ...    language=klingon
    PATCH
    ...    ${API_URL}/api/v1/me/account
    ...    json=${body}    headers=${headers}    expected_status=422

    Stored Language Should Be    fr

An Account Sets Only Its Own Language
    [Documentation]    There is no identifier on the payload to name another.
    ...
    ...    The account changed comes from the credential, so an assistant
    ...    switching to English cannot switch anybody else. Asserted by
    ...    changing one account and reading the other back.
    [Tags]    smoke    i18n    quote-language    access
    ${before}=    Language Of    ${MANAGER_EMAIL}
    Set The Stored Language To    en

    ${after}=    Language Of    ${MANAGER_EMAIL}
    Should Be Equal    ${after}    ${before}
    ...    msg=Changing one account's language changed another's.


*** Keywords ***
Snapshot The Language And Open
    [Documentation]    Record the account's language, then open the browser.
    ...
    ...    Recorded before anything runs. The account is seeded and cannot be
    ...    created, so the only way this suite stays runnable twice is to put
    ...    back exactly what it found.
    ${account}=    Account As Stored
    Set Suite Variable    ${ORIGINAL_LANGUAGE}    ${account}[language]
    Open The Application

Restore The Language And Close
    [Documentation]    Put the language back, then close the browser.
    Run Keyword And Ignore Error    Restore The Language
    Close The Application

Restore The Language And Sign Out
    [Documentation]    Undo a test that switched it, then end the session.
    Run Keyword And Ignore Error    Restore The Language
    Run Keyword And Ignore Error    Switch Language To    fr
    Sign Out

Restore The Name And Language Then Sign Out
    [Documentation]    Undo an edited display name and language, then sign out.

    ...    Arguments:
    ...        name: The display name the account had before the test.
    [Arguments]    ${name}
    Run Keyword And Ignore Error    Set The Account To    ${name}    ${ORIGINAL_LANGUAGE}
    Run Keyword And Ignore Error    Switch Language To    fr
    Sign Out

Account As Stored
    [Documentation]    Read the signed-in account as the server holds it.

    ...    Returns:
    ...        dict: The stored account.
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/account    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Language Of
    [Documentation]    Read one account's stored language.

    ...    Arguments:
    ...        email: The account to sign in as.
    ...
    ...    Returns:
    ...        str: Its stored language code.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/account    headers=${headers}    expected_status=200
    RETURN    ${response.json()}[language]

Stored Language Should Be
    [Documentation]    Assert the account's stored language.

    ...    Arguments:
    ...        expected: The language code the account should hold.
    [Arguments]    ${expected}
    ${account}=    Account As Stored
    Should Be Equal    ${account}[language]    ${expected}
    ...    msg=The account holds ${account}[language] rather than ${expected}.

Set The Stored Language To
    [Documentation]    Write a language onto the account through the API.

    ...    Arguments:
    ...        code: The language code to store.
    ...
    ...    Through the API rather than the toggle: several tests need the
    ...    account to *already* be in a language before the browser opens, and
    ...    clicking to get there would be testing the toggle in the setup of
    ...    the test that tests the toggle.
    [Arguments]    ${code}
    ${account}=    Account As Stored
    Set The Account To    ${account}[full_name]    ${code}

Set The Account To
    [Documentation]    Write a display name and a language onto the account.

    ...    Arguments:
    ...        name: The display name to store.
    ...        code: The language code to store.
    [Arguments]    ${name}    ${code}
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${account}=    Account As Stored
    ${body}=    Create Dictionary
    ...    full_name=${name}
    ...    email=${account}[email]
    ...    language=${code}
    PATCH
    ...    ${API_URL}/api/v1/me/account
    ...    json=${body}    headers=${headers}    expected_status=200

Restore The Language
    [Documentation]    Write the language back as the suite found it.
    Run Keyword And Return If    '${ORIGINAL_LANGUAGE}' == '${EMPTY}'    No Operation
    Set The Stored Language To    ${ORIGINAL_LANGUAGE}

Take A Screenshot On Failure
    [Documentation]    Capture the screen a failing test left behind.
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
