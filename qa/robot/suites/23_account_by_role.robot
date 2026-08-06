*** Settings ***
Documentation    The same account page, seen by the two roles that differ on it.
...
...              Contract type and qualifications are locked for an assistant
...              and editable for a manager. That is one screen with two
...              behaviours, and a suite that only ever signs in as one of them
...              proves half of it — the half that happens to pass.
...
...              Suite 14 covers the assistant's view in depth. This one covers
...              the difference, from both sides, and asserts that the server
...              enforces it independently of what the screen offers.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application
Suite Teardown   Restore Everything And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${QA_CERTIFICATION}     QA-Role-Qualification
${ORIGINAL_NAME}        ${EMPTY}


*** Test Cases ***
Every Role Gets An Account Page At All
    [Documentation]    **The regression this section was added for.**
    ...
    ...    The account screen was built on the *assistant* record, which a
    ...    manager and an administrator do not have — the request answers 403
    ...    for them — so the whole page rendered as one red error, and nothing
    ...    on it said why. Walked as all three roles: a suite that only ever
    ...    signs in as an assistant would have stayed green throughout.
    [Tags]    smoke    account    access
    FOR    ${email}    IN    ${ASSISTANT_EMAIL}    ${MANAGER_EMAIL}    ${ADMIN_EMAIL}
        Sign In As    ${email}
        Navigate To    /me
        Wait For Elements State    [data-testid="account-section"]    visible
        ...    message=${email} has no account section on /me.
        Get Property    [data-testid="account-email"]    value    ==    ${email}
        Sign Out
    END

An Account With No Assistant Record Says So
    [Documentation]    An explanation, not an error and not a blank page.
    ...
    ...    A manager has no schedule, no customer portfolio and no round
    ...    photograph, because those belong to the person being scheduled. The
    ...    page says that in a sentence rather than leaving four sections
    ...    mysteriously absent.
    [Tags]    smoke    account
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /me
    ${bound}=    Manager Assistant Record
    IF    '${bound}' == 'None'
        Wait For Elements State    [data-testid="no-assistant-record"]    visible
        ${absent}=    Get Element Count    [data-testid="absences-section"]
        Should Be Equal As Integers    ${absent}    0
    ELSE
        # The seeder may bind the manager to an assistant record. Then the
        # assistant sections are correct to be there, and the notice is not.
        Wait For Elements State    [data-testid="absences-section"]    visible
    END
    [Teardown]    Sign Out

The Display Name Is The Holder's Own To Change
    [Documentation]    Saved for real, then put back.
    ...
    ...    The *name* rather than the address: changing the sign-in address is
    ...    what the campaign signs in with, and a run that failed between the
    ...    save and the restore would lock every later run out of the account.
    ...    The name has no such consequence, so it is the field that can be
    ...    exercised honestly.
    [Tags]    smoke    account
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /me
    ${original}=    Get Property    [data-testid="account-full-name"]    value
    Set Suite Variable    ${ORIGINAL_NAME}    ${original}

    Fill Text    [data-testid="account-full-name"]    ${original} QA
    Wait For Elements State    [data-testid="save-account"]    enabled
    Click    [data-testid="save-account"]
    Wait For Elements State    [data-testid="account-saved"]    visible

    ${stored}=    Account Of    ${MANAGER_EMAIL}
    Should Be Equal    ${stored}[full_name]    ${original} QA
    [Teardown]    Restore The Display Name

Saving Is Refused Until Something Changes
    [Documentation]    An untouched account has nothing to store.
    [Tags]    account
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="account-section"]    visible
    Get Element States    [data-testid="save-account"]    contains    disabled
    [Teardown]    Sign Out

Saving Is Refused While A Field Is Unusable
    [Documentation]    A blank name or a malformed address never leaves the page.
    ...
    ...    Both are refused by the server as well — the payload model checks
    ...    them — but a form that lets somebody press Save and then reports a
    ...    422 has told them nothing they could not have been told before they
    ...    pressed it.
    [Tags]    smoke    account
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="account-full-name"]    visible

    Fill Text    [data-testid="account-full-name"]    ${EMPTY}
    Get Element States    [data-testid="save-account"]    contains    disabled

    ${name}=    Account Of    ${MANAGER_EMAIL}
    Fill Text    [data-testid="account-full-name"]    ${name}[full_name] QA
    Fill Text    [data-testid="account-email"]    not-an-address
    Get Element States    [data-testid="save-account"]    contains    disabled
    [Teardown]    Reload And Sign Out

An Address Another Account Holds Is Reported On The Page
    [Documentation]    The conflict, where the person who caused it can see it.
    ...
    ...    Suite-level API assertions prove the server refuses it. This proves
    ...    the refusal reaches the screen: a 409 swallowed by the client would
    ...    leave the form looking as though the save had worked, and the holder
    ...    would find out at the next sign-in.
    [Tags]    smoke    account
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="account-email"]    visible
    Fill Text    [data-testid="account-email"]    ${MANAGER_EMAIL}
    Wait For Elements State    [data-testid="save-account"]    enabled
    Click    [data-testid="save-account"]
    Wait For Elements State    [data-testid="account-error"]    visible

    # And nothing was stored, which is what the message is claiming.
    ${stored}=    Account Of    ${ASSISTANT_EMAIL}
    Should Be Equal    ${stored}[email]    ${ASSISTANT_EMAIL}
    [Teardown]    Reload And Sign Out

Each Locked Field Says Who Owns It
    [Documentation]    A chip that explains, rather than a disabled box.
    ...
    ...    A disabled input says "you cannot type here". A locked chip with a
    ...    tooltip says who to ask, which is the difference between somebody
    ...    confused and somebody who knows what to do next.
    [Tags]    account
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    FOR    ${field}    IN
    ...    account-role    account-active    account-hca-id    account-company
        Wait For Elements State    [data-testid="${field}"]    visible
        # The value, not the tooltip. MUI renders the tooltip text only while
        # the pointer is over the chip, so asserting on it here would assert on
        # an element that is not in the document.
        ${text}=    Get Text    [data-testid="${field}"]
        Should Not Be Empty    ${text}
        ...    msg=${field} is locked but shows nothing at all.
    END
    [Teardown]    Sign Out

A Privileged Field Is Refused However It Arrives
    [Documentation]    **What the account page's editability actually rests on.**
    ...
    ...    The payload model carries a display name and an address and nothing
    ...    else, so a request naming a role is parsed without it rather than
    ...    obeyed. Sent by hand: the screen offers no such control, and a test
    ...    that only checked the screen would prove only that the button was
    ...    missing.
    [Tags]    smoke    account    access
    ${before}=    Account Of    ${ASSISTANT_EMAIL}
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    full_name=${before}[full_name]
    ...    email=${before}[email]
    ...    role=admin
    ...    is_active=${False}
    PATCH
    ...    ${API_URL}/api/v1/me/account
    ...    json=${body}    headers=${headers}    expected_status=200

    ${after}=    Account Of    ${ASSISTANT_EMAIL}
    Should Be Equal    ${after}[role]    ${before}[role]
    Should Be Equal    ${after}[is_active]    ${before}[is_active]

An Address Another Account Holds Is Refused
    [Documentation]    Reported as a conflict, not as a crash.
    ...
    ...    The column is unique. Without the service's own check this would
    ...    surface as a database integrity error and be answered 500 — a typo
    ...    reported as a server fault, with nothing saying what to correct.
    [Tags]    account
    ${assistant}=    Account Of    ${ASSISTANT_EMAIL}
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    full_name=${assistant}[full_name]
    ...    email=${MANAGER_EMAIL}
    PATCH
    ...    ${API_URL}/api/v1/me/account
    ...    json=${body}    headers=${headers}    expected_status=409

Keeping Your Own Address Is Not A Conflict
    [Documentation]    Or the display name could never be saved at all.
    ...
    ...    The screen sends both fields on every save, so somebody changing only
    ...    their name sends their own address back unchanged. Comparing
    ...    addresses alone would call that a clash and refuse every save.
    [Tags]    smoke    account
    ${assistant}=    Account Of    ${ASSISTANT_EMAIL}
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    full_name=${assistant}[full_name]
    ...    email=${assistant}[email]
    PATCH
    ...    ${API_URL}/api/v1/me/account
    ...    json=${body}    headers=${headers}    expected_status=200

An Assistant Sees Employment Locked
    [Documentation]    Chips, no inputs, no save button.
    [Tags]    smoke    account    access
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="employment-section"]    visible

    ${inputs}=    Get Element Count    [data-testid="employment-section"] input
    Should Be Equal As Integers    ${inputs}    0
    ${save}=    Get Element Count    [data-testid="save-employment"]
    Should Be Equal As Integers    ${save}    0
    [Teardown]    Sign Out

An Assistant Sees The Locked Fields Explained
    [Documentation]    A tooltip naming who owns them, not a bare disabled box.
    ...
    ...    A disabled input says "you cannot type here". A locked chip with
    ...    "set by your manager" says who to ask, which is the difference
    ...    between a confused assistant and one who knows what to do next.
    [Tags]    account
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    Hover    [data-testid="contract-type"]
    Wait For Elements State    .MuiTooltip-tooltip    visible
    Get Text    .MuiTooltip-tooltip    !=    ${EMPTY}
    [Teardown]    Sign Out

A Manager With An Assistant Record May Edit Employment
    [Documentation]    The same section, offering a select and a save button.
    ...
    ...    Skipped when the seeded managers hold no assistant record: the
    ...    difference is only observable on an account that has one, and that
    ...    is a fact about the seed rather than a defect in the screen.
    [Tags]    smoke    account    access
    ${manager_hca}=    Manager Assistant Record
    Skip If    '${manager_hca}' == 'None'
    ...    No seeded manager is also an assistant; nothing to observe.

    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="contract-type-select"]    visible
    Wait For Elements State    [data-testid="save-employment"]         visible
    [Teardown]    Sign Out

The Server Refuses A Locked Field However It Arrives
    [Documentation]    The screen decides what to offer; the server what it accepts.
    ...
    ...    **The test the whole arrangement rests on.** Hiding a control proves
    ...    nothing — anybody can send the request by hand. The self-service
    ...    payload has no ``contract_type``, ``certifications`` or ``role``
    ...    field at all, so a request carrying them is not refused, it is
    ...    *unchanged by them*: the fields are dropped before any code sees one.
    [Tags]    smoke    account    access

    ${before}=    Assistant Profile
    ${token}=     Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=   Authorisation Header    ${token}

    ${address}=    Create Dictionary
    ...    street=${before}[address][street]
    ...    postal_code=${before}[address][postal_code]
    ...    city=${before}[address][city]
    ...    country=France
    ${forged}=    Create Dictionary    name=${QA_CERTIFICATION}
    ${body}=    Create Dictionary
    ...    first_name=${before}[first_name]
    ...    last_name=${before}[last_name]
    ...    phone_number=${before}[phone_number]
    ...    email=${before}[email]
    ...    address=${address}
    ...    contract_type=cdi
    ...    certifications=${{ [$forged] }}
    ...    role=admin

    PATCH    ${API_URL}/api/v1/me/hca
    ...    json=${body}    headers=${headers}    expected_status=200

    ${after}=    Assistant Profile
    Should Be Equal    ${after}[contract_type]    ${before}[contract_type]
    ${names}=    Evaluate    [c["name"] for c in $after["certifications"]]
    Should Not Contain    ${names}    ${QA_CERTIFICATION}
    Should Be Equal As Integers
    ...    ${{ len($after["certifications"]) }}
    ...    ${{ len($before["certifications"]) }}

An Assistant Cannot Promote Themselves
    [Documentation]    The role is an administrator's to grant, and only theirs.
    [Tags]    smoke    account    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${me}=    GET    ${API_URL}/api/v1/auth/me    headers=${headers}
    POST
    ...    ${API_URL}/api/v1/users/${me.json()}[id]/promote
    ...    headers=${headers}
    ...    expected_status=403

An Assistant Cannot Read A Colleague's Record
    [Documentation]    There is no path parameter on /me to tamper with.
    ...
    ...    The manager-facing route exists and is guarded; this asserts the
    ...    guard rather than the absence of a link.
    [Tags]    account    access
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    GET
    ...    ${API_URL}/api/v1/hcas    headers=${headers}    expected_status=403


*** Keywords ***
Restore Everything And Close
    [Documentation]    Strip anything a failed test may have stored.
    Run Keyword And Ignore Error    Remove The QA Qualification
    Run Keyword And Ignore Error    Restore The Display Name
    Close The Application

Reload And Sign Out
    [Documentation]    Discard an unsaved form, then end the session.
    ...
    ...    Reloaded first: these tests leave edits in the inputs that were never
    ...    saved, and the next test signing in would find the previous one's
    ...    typing still on screen.
    Run Keyword And Ignore Error    Reload
    Sign Out

Account Of
    [Documentation]    Read an account as the server currently holds it.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/account
    ...    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Restore The Display Name
    [Documentation]    Put the manager's name back, through the API.
    ...
    ...    Through the API rather than the screen: a test that failed mid-save
    ...    left the browser on a form, and clicking a button that may not be
    ...    there would fail the teardown for the same reason the test did —
    ...    leaving the renamed account behind for every run after.
    Run Keyword And Return If    '${ORIGINAL_NAME}' == '${EMPTY}'    No Operation
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    full_name=${ORIGINAL_NAME}    email=${MANAGER_EMAIL}
    PATCH
    ...    ${API_URL}/api/v1/me/account
    ...    json=${body}    headers=${headers}    expected_status=200
    Set Suite Variable    ${ORIGINAL_NAME}    ${EMPTY}

Assistant Profile
    [Documentation]    Read the seeded assistant's own record.
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/me/hca    headers=${headers}    expected_status=200
    RETURN    ${response.json()}

Manager Assistant Record
    [Documentation]    Return the manager's assistant identifier, or ``None``.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET    ${API_URL}/api/v1/auth/me    headers=${headers}
    RETURN    ${response.json()}[hca_id]

Remove The QA Qualification
    [Documentation]    Belt and braces, in case a request above ever succeeds.
    ...
    ...    It should never have been stored — that is what the suite asserts —
    ...    but a teardown that assumes the assertion passed is a teardown that
    ...    does nothing on the one run where it mattered.
    ${profile}=    Assistant Profile
    ${names}=    Evaluate    [c["name"] for c in $profile["certifications"]]
    Return From Keyword If    "${QA_CERTIFICATION}" not in ${names}

    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${kept}=    Evaluate
    ...    [c for c in $profile["certifications"] if c["name"]!="${QA_CERTIFICATION}"]
    ${body}=    Create Dictionary
    ...    contract_type=${profile}[contract_type]
    ...    certifications=${kept}
    PATCH
    ...    ${API_URL}/api/v1/hcas/${profile}[id]/employment
    ...    json=${body}    headers=${headers}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
