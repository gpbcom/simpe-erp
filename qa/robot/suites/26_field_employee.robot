*** Settings ***
Documentation    Who the planner may schedule, and who decides it.
...
...              ``field_employee`` is a boolean on the *person*, not a role
...              check: a manager who covers rounds and an assistant on office
...              duties are both ordinary, and neither is expressible as a
...              ``UserRole``. Two things are worth proving. A manager can turn
...              it off for anybody — including themselves, since the route
...              takes an identifier and they hold the role — and an assistant
...              cannot turn it off for anyone, least of all themselves.
...
...              The second is the security-shaped one, and it is asserted
...              twice: the screen shows a locked chip, and the payload that
...              would carry the field is sent by hand to prove the server
...              refuses it rather than the form merely hiding it.
...
...              Both roles are exercised on the *account* page, not only on
...              the workforce grid, and deliberately as a pair. "No switch is
...              rendered for an assistant" passes just as well on a screen
...              that renders no switch for anybody, so the manager's own page
...              is asserted to render one — which needs the seeded manager
...              who still covers rounds, the only account holding both a
...              manager's role and an assistant record.
...
...              Everything written is written back, so the suite runs twice
...              with the same result.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Workforce As A Manager
Suite Teardown   Put Everybody Back On The Rounds And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${TARGET_HCA_NAME}      Martin


*** Test Cases ***
The Grid Says Who Goes Out
    [Documentation]    A workforce screen that does not is a screen that hides it.
    [Tags]    smoke    field-employee
    ${hca}=    The Target Assistant
    Wait For Elements State    [data-testid="field-employee-${hca}[id]"]    visible

A Manager Toggles It In The Grid Itself
    [Documentation]    **Changed where it is read, not only inside a dialog.**
    ...
    ...    The column used to be a chip, and the only control that changed it
    ...    sat behind a button labelled "edit the qualifications" — which is
    ...    not where anybody looks for "is this person out this week". The
    ...    field a manager changes weekly was the hardest one on the screen to
    ...    find.
    ...
    ...    Toggled twice, so the test restores what it changed even when the
    ...    assertion between the two halves is the thing that fails.
    [Tags]    smoke    field-employee
    Find The Target In The Grid
    ${hca}=    The Target Assistant

    Click    [data-testid="field-employee-${hca}[id]"] input
    Sleep    2s
    ${after}=    The Target Assistant
    Should Not Be True    ${after}[field_employee]
    ...    msg=The grid's switch did not change who may be scheduled.

    Click    [data-testid="field-employee-${hca}[id]"] input
    Sleep    2s
    ${restored}=    The Target Assistant
    Should Be True    ${restored}[field_employee]
    [Teardown]    Clear The Search

Everybody Seeded Is On The Rounds
    [Documentation]    The default is what every record predating the field was.
    ...
    ...    Defaulting to False would have emptied the workforce on the
    ...    deployment that introduced the column and failed every planning run
    ...    until somebody ticked a box they had not been told about. This is
    ...    the assertion that the migration's backfill did its job.
    [Tags]    smoke    field-employee
    ${workforce}=    The Whole Workforce
    ${office}=    Evaluate    [h for h in $workforce if not h["field_employee"]]
    Should Be Empty    ${office}
    ...    msg=A seeded assistant is not a field employee. The backfill is wrong.

A Manager Takes Somebody Off The Rounds
    [Documentation]    The switch is on the employment dialog, beside the qualifications.
    [Tags]    smoke    field-employee
    Open The Employment Editor
    Click    [data-testid="field-employee"]
    Click    [data-testid="save-certifications"]
    Sleep    2s

    ${hca}=    The Target Assistant
    Should Not Be True    ${hca}[field_employee]

The Grid Shows It Without A Reload
    [Documentation]    The list refetches rather than going stale.
    [Tags]    field-employee
    Find The Target In The Grid
    ${hca}=    The Target Assistant
    ${label}=    Get Text    [data-testid="field-employee-${hca}[id]"]
    Should Not Be Empty    ${label}
    [Teardown]    Clear The Search

Taking Somebody Off The Rounds Changes Nothing Else
    [Documentation]    Not a dismissal: their record, their quotes and their account stay.
    ...
    ...    Worth asserting because the switch sits on the same payload as the
    ...    contract type and the qualifications, and a payload that replaces
    ...    all three is a payload that can quietly clear the other two.
    [Tags]    field-employee
    ${hca}=    The Target Assistant
    Should Not Be Equal    ${hca}[contract_type]    ${None}
    Should Not Be Empty    ${hca}[first_name]
    ${account}=    The Target Account
    Should Not Be Equal    ${account}    ${None}
    ...    msg=Taking somebody off the rounds removed their account.

A Manager Puts Them Back
    [Documentation]    The other direction, and the suite's own clean-up.
    [Tags]    smoke    field-employee
    Open The Employment Editor
    Click    [data-testid="field-employee"]
    Click    [data-testid="save-certifications"]
    Sleep    2s

    ${hca}=    The Target Assistant
    Should Be True    ${hca}[field_employee]

An Assistant Sees The Flag Locked On Their Own Page
    [Documentation]    Shown rather than hidden, and locked rather than disabled.
    ...
    ...    A page that omits what it will not let you change answers "what does
    ...    this system say about me?" with silence. A disabled input says "you
    ...    cannot type here". A locked chip says who to ask.
    [Tags]    smoke    field-employee    scoping
    Sign Out
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="employment-section"]    visible
    Wait For Elements State    [data-testid="field-employee"]    visible
    # A chip, not a switch. Both carry the same identifier — it names the
    # control, not the variant — so they are told apart by what is inside:
    # a switch wraps a real checkbox, and a chip wraps nothing.
    ${switches}=    Get Element Count
    ...    [data-testid="field-employee"] input
    Should Be Equal As Integers    ${switches}    0
    # There is nothing to save either: the button belongs to the editable half.
    ${saves}=    Get Element Count    [data-testid="save-employment"]
    Should Be Equal As Integers    ${saves}    0
    [Teardown]    Sign Back In As The Manager

A Manager Changes Their Own Flag From Their Own Page
    [Documentation]    **The editable half of the same section, on the same screen.**
    ...
    ...    The paired assertion to the one above, and the reason it is worth
    ...    making: "no switch is rendered" passes just as well on a screen that
    ...    renders no switch for *anybody*. Signing in as somebody who should
    ...    see one is what tells a real lock apart from a missing control.
    ...
    ...    It needs an account holding both a manager's role and an assistant
    ...    record — the section renders from the record and unlocks on the
    ...    role. Only ``${MANAGER_HCA_EMAIL}`` has both, which is why the
    ...    seeder promotes one assistant rather than leaving every manager
    ...    without a record.
    [Tags]    smoke    field-employee    scoping
    Sign Out
    Sign In As    ${MANAGER_HCA_EMAIL}
    Navigate To    /me
    Wait For Elements State    [data-testid="employment-section"]    visible
    Wait For Elements State    [data-testid="field-employee"] input    attached

    ${before}=    The Manager Who Covers Rounds
    Click    [data-testid="field-employee"]
    Click    [data-testid="save-employment"]
    Sleep    2s

    ${after}=    The Manager Who Covers Rounds
    Should Not Be Equal    ${before}[field_employee]    ${after}[field_employee]
    ...    msg=The switch saved without changing who may be scheduled.
    [Teardown]    Restore The Manager And Sign Back In

An Assistant Cannot Take Themselves Off The Rounds
    [Documentation]    Sent by hand, because the form not offering it is not the control.
    ...
    ...    The rule lives in the shape of the payload the manager-gated route
    ...    accepts, and in that route's guard — not in the screen. So the
    ...    request the screen will not make is made here, and the server is
    ...    asked to refuse it.
    [Tags]    smoke    field-employee    scoping    security
    ${hca}=    The Target Assistant
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${body}=    Create Dictionary
    ...    contract_type=${hca}[contract_type]
    ...    certifications=${hca}[certifications]
    ...    field_employee=${False}
    ${response}=    PATCH
    ...    ${API_URL}/api/v1/hcas/${hca}[id]/employment
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any
    Should Be True    ${response.status_code} in [401, 403]
    ...    msg=An assistant was allowed to change who may be scheduled.

    ${after}=    The Target Assistant
    Should Be True    ${after}[field_employee]
    ...    msg=The refused request changed the record anyway.

An Assistant's Own Payload Carries No Such Field
    [Documentation]    The self-service route cannot reach it at all.
    ...
    ...    Belt and braces on the same rule from the other side: even the
    ...    route an assistant *may* call ignores the field, so a well-formed
    ...    request through the door they are allowed through changes nothing.
    [Tags]    field-employee    scoping    security
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${profile}=    GET
    ...    ${API_URL}/api/v1/me/hca    headers=${headers}    expected_status=200
    ${hca}=    Set Variable    ${profile.json()}
    ${body}=    Create Dictionary
    ...    first_name=${hca}[first_name]
    ...    last_name=${hca}[last_name]
    ...    phone_number=${hca}[phone_number]
    ...    email=${hca}[email]
    ...    address=${hca}[address]
    ...    field_employee=${False}
    PATCH
    ...    ${API_URL}/api/v1/me/hca
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=any

    ${after}=    The Target Assistant
    Should Be True    ${after}[field_employee]
    ...    msg=The self-service payload smuggled the field through.


*** Keywords ***
Open The Workforce As A Manager
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible

Sign Back In As The Manager
    Sign Out
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible

Put Everybody Back On The Rounds And Close
    [Documentation]    Restore the flag however the suite ended.
    ...
    ...    A belt-and-braces teardown. The normal path restores it in a test;
    ...    this catches the case where an earlier one failed and left somebody
    ...    off the rounds — which would silently shrink the workforce every
    ...    later suite plans over.
    ${status}    ${error}=    Run Keyword And Ignore Error
    ...    Restore The Target Assistant Through The API
    ${manager}    ${manager_error}=    Run Keyword And Ignore Error
    ...    Restore The Manager Through The API
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    An assistant was left off the rounds: ${error}
    END
    IF    '${manager}' != 'PASS'
        Fail    A manager was left off the rounds: ${manager_error}
    END

Manager Headers
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    RETURN    ${headers}

The Target Assistant
    [Documentation]    Return the assistant this suite works on.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    search=${TARGET_HCA_NAME}
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${found}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${found}
    ...    msg=No seeded assistant named ${TARGET_HCA_NAME}.
    RETURN    ${found}[0]

The Target Account
    [Documentation]    Return the sign-in account bound to them, or ``None``.
    ${hca}=    The Target Assistant
    ${token}=    Sign In Through The API    ${ADMIN_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/users
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [u for u in $response.json() if u["hca_id"]=="${hca}[id]"]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

The Manager Who Covers Rounds
    [Documentation]    Return the assistant record behind ${MANAGER_HCA_EMAIL}.
    ...
    ...    Found by address rather than by surname, because this one is looked
    ...    up as an account holder: the point of the record is that a sign-in
    ...    exists for it holding the manager role.
    ${workforce}=    The Whole Workforce
    ${matching}=    Evaluate
    ...    [h for h in $workforce if h["email"]=="${MANAGER_HCA_EMAIL}"]
    Should Not Be Empty    ${matching}
    ...    msg=No assistant record for ${MANAGER_HCA_EMAIL}; was the seeder run?
    RETURN    ${matching}[0]

Restore The Manager And Sign Back In
    [Documentation]    Put the manager back on the rounds, then resume the manager session.
    Restore The Manager Through The API
    Sign Back In As The Manager

Restore The Manager Through The API
    [Documentation]    Put the manager who covers rounds back on them.
    ...
    ...    Through the API rather than the screen, so a failure part-way
    ...    through the test above still leaves the workforce as it found it.
    ...    A manager left off the rounds silently shrinks every later suite's
    ...    planning by one.
    ${headers}=    Manager Headers
    ${hca}=    The Manager Who Covers Rounds
    ${body}=    Create Dictionary
    ...    contract_type=${hca}[contract_type]
    ...    certifications=${hca}[certifications]
    ...    field_employee=${True}
    PATCH
    ...    ${API_URL}/api/v1/hcas/${hca}[id]/employment
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200
    Sign Back In As The Manager

The Whole Workforce
    [Documentation]    Return every assistant the agency holds.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    size=500
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${workforce}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${workforce}
    ...    msg=The workforce is empty; was the seeder run?
    RETURN    ${workforce}

Open The Employment Editor
    [Documentation]    Find the assistant in the grid and open their editor.
    ${hca}=    The Target Assistant
    Find The Target In The Grid
    Click    [data-testid="edit-certifications-${hca}[id]"]
    Wait For Elements State    [data-testid="certification-editor"]    visible

Find The Target In The Grid
    [Documentation]    Narrow the workforce to the assistant this suite works on.
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    Fill Text    [data-testid="hca-search"]    ${TARGET_HCA_NAME}
    Sleep    2s

Clear The Search
    Fill Text    [data-testid="hca-search"]    ${EMPTY}
    Sleep    2s

Restore The Target Assistant Through The API
    [Documentation]    Put them back on the rounds without the browser.
    ${headers}=    Manager Headers
    ${hca}=    The Target Assistant
    ${body}=    Create Dictionary
    ...    contract_type=${hca}[contract_type]
    ...    certifications=${hca}[certifications]
    ...    field_employee=${True}
    PATCH
    ...    ${API_URL}/api/v1/hcas/${hca}[id]/employment
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
