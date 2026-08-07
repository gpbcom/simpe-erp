*** Settings ***
Documentation    The certification catalogue — what the agency recognises.
...
...              Everything a service can require and an assistant can hold is
...              keyed on a code from this screen, so three rules are worth
...              proving rather than trusting: a code cannot be renamed once it
...              exists, a malformed one is refused before it can be stored,
...              and an entry something still refers to cannot be deleted.
...
...              The third is the one with no database behind it. The
...              references live in a JSON array and in a nullable column with
...              no foreign key on either, so the service's own count is all
...              that stands between a delete and a requirement pointing at
...              nothing — which fails every planning run it touches.
...
...              The entry this suite creates is deleted by the last test and
...              again in the teardown, so the suite runs twice with the same
...              result.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Certification Catalogue
Suite Teardown   Remove The QA Certification And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
# Filled in by the setup: a code no other run produces, so two runs against the
# same stack do not collide on the unique index.
${QA_CODE}          ${EMPTY}
${QA_LABEL}         ${EMPTY}


*** Test Cases ***
The Catalogue Lists What The Agency Recognises
    [Documentation]    The seeded qualifications are there to be required.
    [Tags]    smoke    certifications
    Wait For Elements State    [data-testid="certifications-grid"]    visible
    ${rows}=    Get Element Count
    ...    [data-testid="certifications-grid"] .MuiDataGrid-row
    Should Be True    ${rows} > 0

The Screen Says What A Certification Is For
    [Documentation]    A catalogue nobody understands is a catalogue nobody fills.
    [Tags]    certifications
    Wait For Elements State    [data-testid="certifications-explained"]    visible

A Malformed Code Is Refused Before It Can Be Stored
    [Documentation]    An accented code is not a code.
    ...
    ...    The code travels into exports and URLs, where an accent is escaped
    ...    differently by every consumer and the same qualification comes back
    ...    as two. The server refuses it; the form says so first, so the
    ...    operator is not told after they press save.
    [Tags]    certifications    validation
    Click    [data-testid="new-certification"]
    Wait For Elements State    [data-testid="certification-dialog"]    visible
    Fill Text    [data-testid="certification-code"]    DÉAES
    Fill Text    [data-testid="certification-label"]    Diplome accentue
    Get Attribute    [data-testid="save-certification"]    disabled
    [Teardown]    Click    [data-testid="cancel-certification"]

A Label Alone Is Not Enough
    [Documentation]    An entry with no code is one nothing can be matched on.
    [Tags]    certifications    validation
    Click    [data-testid="new-certification"]
    Wait For Elements State    [data-testid="certification-dialog"]    visible
    Fill Text    [data-testid="certification-label"]    Sans code
    Get Attribute    [data-testid="save-certification"]    disabled
    [Teardown]    Click    [data-testid="cancel-certification"]

A Qualification Is Added And Stored
    [Documentation]    The whole point of the screen.
    [Tags]    smoke    certifications
    Click    [data-testid="new-certification"]
    Wait For Elements State    [data-testid="certification-dialog"]    visible
    Fill Text    [data-testid="certification-code"]    ${QA_CODE}
    Fill Text    [data-testid="certification-label"]    ${QA_LABEL}
    Click    [data-testid="save-certification"]
    Sleep    2s

    ${stored}=    The QA Certification
    Should Not Be Equal    ${stored}    ${None}
    ...    msg=The qualification was not stored.
    Should Be Equal    ${stored}[label]    ${QA_LABEL}

The Stored Qualification Shows On The Grid
    [Documentation]    The list refetches rather than going stale.
    [Tags]    certifications
    Navigate To    /certifications
    Wait For Elements State    [data-testid="certifications-grid"]    visible
    Get Text    [data-testid="certifications-grid"]    *=    ${QA_CODE}

The Code Cannot Be Changed Once The Entry Exists
    [Documentation]    Renaming it would disqualify everybody holding it.
    ...
    ...    The input is locked, and the payload carries no ``code`` at all —
    ...    a locked input is a courtesy, the absent field is the control. This
    ...    asserts the courtesy; ``tests/api`` asserts the control.
    [Tags]    smoke    certifications
    Open The QA Certification
    Get Attribute    [data-testid="certification-code"]    disabled
    [Teardown]    Click    [data-testid="cancel-certification"]

The Label Is Editable And The Change Is Stored
    [Documentation]    Renaming what a manager reads is safe; renaming the key is not.
    [Tags]    certifications
    Open The QA Certification
    Fill Text    [data-testid="certification-label"]    ${QA_LABEL} modifie
    Click    [data-testid="save-certification"]
    Sleep    2s

    ${stored}=    The QA Certification
    Should Be Equal    ${stored}[label]    ${QA_LABEL} modifie
    Should Be Equal    ${stored}[code]    ${QA_CODE}

Retiring An Entry Keeps It Listed And Marked
    [Documentation]    Retired is a state, not an absence.
    ...
    ...    A manager wondering why they cannot require a qualification needs to
    ...    see that it exists and is retired. A screen that simply omitted it
    ...    would answer that question with silence.
    [Tags]    certifications
    Open The QA Certification
    Click    [data-testid="certification-active"]
    Click    [data-testid="save-certification"]
    Sleep    2s

    ${stored}=    The QA Certification
    Should Not Be True    ${stored}[is_active]
    Get Text    [data-testid="certification-status-${QA_CODE}"]    !=    ${EMPTY}
    [Teardown]    Put The QA Certification Back In Use

A Qualification Somebody Holds Cannot Be Deleted
    [Documentation]    The check that stands in for a foreign key that cannot exist.
    ...
    ...    The reference lives in a nullable column with no constraint on it,
    ...    so nothing at the database level would stop this. The refusal names
    ...    what still holds it and offers retirement instead — "cannot delete"
    ...    with no reason is a message somebody works around.
    [Tags]    smoke    certifications
    Give The QA Certification To An Assistant
    Open The QA Certification
    Click    [data-testid="delete-certification"]
    Wait For Elements State    [data-testid="certification-dialog-error"]    visible
    ${message}=    Get Text    [data-testid="certification-dialog-error"]
    Should Contain    ${message}    assistant
    [Teardown]    Take The QA Certification Back And Close The Dialog

A Qualification A Service Requires Cannot Be Deleted
    [Documentation]    The other half of the same rule, on the other reference.
    ...
    ...    This one lives in a JSON array, which a foreign key cannot reach
    ...    inside at all. Deleting through it would leave a service requiring
    ...    something nobody can hold, and every run touching that service would
    ...    fail with a diagnosis that reads as a staffing problem.
    [Tags]    certifications
    Require The QA Certification On A Service
    Open The QA Certification
    Click    [data-testid="delete-certification"]
    Wait For Elements State    [data-testid="certification-dialog-error"]    visible
    ${message}=    Get Text    [data-testid="certification-dialog-error"]
    Should Contain    ${message}    service
    [Teardown]    Stop Requiring The QA Certification And Close The Dialog

An Unreferenced Qualification Is Deleted
    [Documentation]    The suite's own clean-up, written as the test it is.
    ...
    ...    Deleting what this run created is what makes the suite runnable
    ...    twice. It is a test rather than a teardown because the delete path
    ...    is worth asserting on its own, now that the two refusals above have
    ...    proved it is not simply always refused.
    [Tags]    smoke    certifications
    Open The QA Certification
    Click    [data-testid="delete-certification"]
    Sleep    2s

    ${stored}=    The QA Certification
    Should Be Equal    ${stored}    ${None}
    ...    msg=The qualification survived its own deletion.


*** Keywords ***
Open The Certification Catalogue
    ${suffix}=    Unique Suffix
    ${digits}=    Replace String    ${suffix}    -    ${EMPTY}
    Set Suite Variable    ${QA_CODE}    QA${digits}
    Set Suite Variable    ${QA_LABEL}    Qualification QA ${suffix}
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /certifications
    Wait For Elements State    [data-testid="certifications-grid"]    visible

Remove The QA Certification And Close
    [Documentation]    Strip this run's entry however the suite ended.
    ...
    ...    A belt-and-braces teardown. The last test does this in the normal
    ...    path; this catches the case where an earlier one failed and left the
    ...    entry — and its references — behind, which would poison the next
    ...    run. Reported rather than ignored, because a cleanup that fails
    ...    quietly breaks tomorrow's run instead of today's.
    ${status}    ${error}=    Run Keyword And Ignore Error
    ...    Strip Every Trace Of The QA Certification
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    The QA certification was left behind: ${error}
    END

Manager Headers
    [Documentation]    Return the bearer header for the seeded manager.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    RETURN    ${headers}

The QA Certification
    [Documentation]    Return this run's catalogue entry, or ``None``.
    ...
    ...    Retired entries are included: several tests here retire it, and a
    ...    lookup that hid them would report the entry as deleted when it is
    ...    merely out of use.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    size=500    include_inactive=true
    ${response}=    GET
    ...    ${API_URL}/api/v1/certifications
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${matching}=    Evaluate
    ...    [e for e in $response.json() if e["code"]=="${QA_CODE}"]
    ${found}=    Set Variable If    ${matching}    ${matching}[0]    ${None}
    RETURN    ${found}

Open The QA Certification
    [Documentation]    Find this run's entry on the grid and open its dialog.
    Navigate To    /certifications
    Wait For Elements State    [data-testid="certifications-grid"]    visible
    Click    [data-testid="edit-certification-${QA_CODE}"]
    Wait For Elements State    [data-testid="certification-dialog"]    visible

Put The QA Certification Back In Use
    [Documentation]    Undo a retirement, so the tests after it still apply.
    ${headers}=    Manager Headers
    ${entry}=    The QA Certification
    ${body}=    Create Dictionary    is_active=${True}
    PATCH
    ...    ${API_URL}/api/v1/certifications/${entry}[id]
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Target Assistant
    [Documentation]    Return the assistant this suite borrows for the refusal.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    search=Martin
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${found}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${found}    msg=No seeded assistant named Martin.
    RETURN    ${found}[0]

Give The QA Certification To An Assistant
    [Documentation]    Attach this run's code to a seeded assistant.
    ...
    ...    Through the API rather than through the editor: what is under test
    ...    here is the *refusal to delete*, and building the fixture by
    ...    clicking would make a failure in the editor read as a failure in the
    ...    catalogue.
    ${headers}=    Manager Headers
    ${hca}=    Target Assistant
    ${held}=    Evaluate
    ...    $hca["certifications"] + [{"name": "${QA_LABEL}", "code": "${QA_CODE}"}]
    ${body}=    Create Dictionary
    ...    contract_type=${hca}[contract_type]
    ...    certifications=${held}
    ...    field_employee=${hca}[field_employee]
    PATCH
    ...    ${API_URL}/api/v1/hcas/${hca}[id]/employment
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Take The QA Certification Back From The Assistant
    [Documentation]    Detach this run's code again.
    ${headers}=    Manager Headers
    ${hca}=    Target Assistant
    ${kept}=    Evaluate
    ...    [c for c in $hca["certifications"] if c["code"]!="${QA_CODE}"]
    ${body}=    Create Dictionary
    ...    contract_type=${hca}[contract_type]
    ...    certifications=${kept}
    ...    field_employee=${hca}[field_employee]
    PATCH
    ...    ${API_URL}/api/v1/hcas/${hca}[id]/employment
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Take The QA Certification Back And Close The Dialog
    Take The QA Certification Back From The Assistant
    Click    [data-testid="cancel-certification"]

Target Service
    [Documentation]    Return the catalogue entry this suite borrows.
    ${headers}=    Manager Headers
    ${params}=    Create Dictionary    size=500    include_inactive=true
    ${response}=    GET
    ...    ${API_URL}/api/v1/intervention-types
    ...    params=${params}
    ...    headers=${headers}
    ...    expected_status=200
    ${types}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${types}    msg=The service catalogue is empty.
    RETURN    ${types}[0]

Require The QA Certification On A Service
    [Documentation]    Make a seeded service require this run's code.
    ${headers}=    Manager Headers
    ${service}=    Target Service
    ${codes}=    Create List    ${QA_CODE}
    ${body}=    Create Dictionary    required_certification_codes=${codes}
    PATCH
    ...    ${API_URL}/api/v1/intervention-types/${service}[id]
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Stop Requiring The QA Certification
    [Documentation]    Put the service back to requiring nothing.
    ...
    ...    An **empty array**, not an omitted field: omitting it means "leave
    ...    the requirement alone", which would leave the service gated on a
    ...    code this run is about to delete.
    ${headers}=    Manager Headers
    ${service}=    Target Service
    ${none}=    Create List
    ${body}=    Create Dictionary    required_certification_codes=${none}
    PATCH
    ...    ${API_URL}/api/v1/intervention-types/${service}[id]
    ...    json=${body}
    ...    headers=${headers}
    ...    expected_status=200

Stop Requiring The QA Certification And Close The Dialog
    Stop Requiring The QA Certification
    Click    [data-testid="cancel-certification"]

Strip Every Trace Of The QA Certification
    [Documentation]    Detach the code everywhere, then delete the entry.
    ...
    ...    In that order, and all three steps, because the service refuses to
    ...    delete an entry anything still refers to — which is exactly the
    ...    behaviour two of these tests set up on purpose.
    Run Keyword And Ignore Error    Take The QA Certification Back From The Assistant
    Run Keyword And Ignore Error    Stop Requiring The QA Certification
    ${entry}=    The QA Certification
    IF    ${entry} is not None
        ${headers}=    Manager Headers
        DELETE
        ...    ${API_URL}/api/v1/certifications/${entry}[id]
        ...    headers=${headers}
        ...    expected_status=204
    END

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
