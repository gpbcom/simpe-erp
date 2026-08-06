*** Settings ***
Documentation    The certification editor — the one thing a manager changes.
...
...              This is the other half of the rule the assistant's account page
...              enforces: an assistant sees their qualifications as locked
...              chips, and a manager edits them here. The full add / save /
...              remove cycle is exercised, and everything it writes is written
...              back, so the suite runs twice with the same result.

Library          Browser
Library          Collections
Library          RequestsLibrary
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Workforce Screen
Suite Teardown   Restore The Assistant And Close
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${TARGET_HCA_NAME}      Martin
${QA_CERTIFICATION}     QA-Qualification-Temporaire


*** Test Cases ***
The Workforce Grid Lists Every Assistant
    [Documentation]    Twelve seeded assistants, with their contract and city.
    [Tags]    smoke    hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    ${rows}=    Get Element Count    [data-testid="hcas-grid"] .MuiDataGrid-row
    Should Be True    ${rows} > 0

Each Row Carries A Portrait Or Initials
    [Documentation]    The same fallback the map pins use.
    [Tags]    hcas
    # The first one. Twelve assistants means twelve avatars, and Playwright's
    # strict mode refuses a wait whose selector resolves to more than one
    # element — so a grid full of portraits failed this as an error about the
    # selector rather than passing. Waiting on the first says what the test
    # means: portraits arrived. How many is the count below.
    Wait For Elements State    [data-testid="hcas-grid"] .MuiAvatar-root >> nth=0
    ...    visible
    ${avatars}=    Get Element Count    [data-testid="hcas-grid"] .MuiAvatar-root
    Should Be True    ${avatars} > 0

The Search Narrows The Grid
    [Documentation]    Typing a name reduces the rows, and clearing restores them.
    [Tags]    smoke    hcas    filtering
    ${all}=    Get Element Count    [data-testid="hcas-grid"] .MuiDataGrid-row
    Fill Text    [data-testid="hca-search"]    ${TARGET_HCA_NAME}
    Sleep    2s
    ${filtered}=    Get Element Count    [data-testid="hcas-grid"] .MuiDataGrid-row
    Should Be True    ${filtered} < ${all}
    Should Be True    ${filtered} > 0
    [Teardown]    Clear The Search

A Search That Matches Nothing Empties The Grid
    [Documentation]    Not an error: simply no rows.
    [Tags]    hcas    filtering    empty-state
    Fill Text    [data-testid="hca-search"]    ZZZZ-personne-de-ce-nom
    Sleep    2s
    ${rows}=    Get Element Count    [data-testid="hcas-grid"] .MuiDataGrid-row
    Should Be Equal As Integers    ${rows}    0
    [Teardown]    Clear The Search

The Editor Opens On The Assistant's Current Qualifications
    [Documentation]    Editing starts from what they hold, not from blank.
    [Tags]    smoke    hcas
    Open The Editor For The Target Assistant
    Wait For Elements State    [data-testid="certification-editor"]    visible
    [Teardown]    Click    [data-testid="cancel-certifications"]

Cancelling Changes Nothing
    [Documentation]    A manager who backs out has backed out.
    ...
    ...    Asserted through the API rather than by looking at the grid: the
    ...    question is whether anything was *stored*, and a grid that has not
    ...    refetched would look unchanged either way.
    [Tags]    hcas
    ${before}=    Certifications Of The Target Assistant
    Open The Editor For The Target Assistant
    Fill Text    [data-testid="new-certification"]    ${QA_CERTIFICATION}
    Click    [data-testid="add-certification"]
    Click    [data-testid="cancel-certifications"]
    Sleep    1s
    ${after}=    Certifications Of The Target Assistant
    Should Be Equal As Integers    ${{ len($before) }}    ${{ len($after) }}

Adding And Saving A Qualification Stores It
    [Documentation]    The whole point of the screen.
    [Tags]    smoke    hcas
    ${before}=    Certifications Of The Target Assistant
    Open The Editor For The Target Assistant
    Fill Text    [data-testid="new-certification"]    ${QA_CERTIFICATION}
    Click    [data-testid="add-certification"]
    Click    [data-testid="save-certifications"]
    Sleep    2s

    ${after}=    Certifications Of The Target Assistant
    ${names}=    Evaluate    [c["name"] for c in $after]
    Should Contain    ${names}    ${QA_CERTIFICATION}
    Should Be True    ${{ len($after) }} == ${{ len($before) }} + 1

The Saved Qualification Shows On The Grid
    [Documentation]    The list refetches rather than going stale.
    [Tags]    hcas
    Navigate To    /hcas
    Fill Text    [data-testid="hca-search"]    ${TARGET_HCA_NAME}
    Sleep    2s
    Get Text    [data-testid="hcas-grid"]    *=    ${QA_CERTIFICATION}
    [Teardown]    Clear The Search

Removing A Qualification Stores The Removal
    [Documentation]    The other direction, and the suite's own clean-up.
    ...
    ...    Removing what the previous test added is what makes this suite
    ...    runnable twice. It is written as a test rather than hidden in a
    ...    teardown because the removal path is worth asserting on its own.
    [Tags]    smoke    hcas
    Open The Editor For The Target Assistant
    ${index}=    Index Of The QA Qualification
    Click    [data-testid="remove-certification-${index}"]
    Click    [data-testid="save-certifications"]
    Sleep    2s

    ${after}=    Certifications Of The Target Assistant
    ${names}=    Evaluate    [c["name"] for c in $after]
    Should Not Contain    ${names}    ${QA_CERTIFICATION}


*** Keywords ***
Open The Workforce Screen
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible

Restore The Assistant And Close
    [Documentation]    Strip the QA qualification however the suite ended.
    ...
    ...    A belt-and-braces teardown. The removal test does this in the normal
    ...    path; this catches the case where an earlier test failed and left the
    ...    qualification behind, which would otherwise poison the next run.
    ...
    ...    Reported rather than ignored. Poisoning the next run is exactly what
    ...    this keyword exists to prevent, so failing to do it is worth a
    ...    failure here — where the cause is still on screen — rather than an
    ...    unexplained one tomorrow.
    ${status}    ${error}=    Run Keyword And Ignore Error
    ...    Remove The QA Qualification Through The API
    Close The Application
    IF    '${status}' != 'PASS'
        Fail    The QA qualification was left on the seeded assistant: ${error}
    END

Clear The Search
    Fill Text    [data-testid="hca-search"]    ${EMPTY}
    Sleep    2s

Target Assistant Id
    [Documentation]    Return the identifier of the assistant under test.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas
    ...    params=${{ {"search": $TARGET_HCA_NAME} }}
    ...    headers=${headers}
    ...    expected_status=200
    ${found}=    Set Variable    ${response.json()}
    Should Not Be Empty    ${found}    msg=No seeded assistant named ${TARGET_HCA_NAME}.
    RETURN    ${found}[0][id]

Certifications Of The Target Assistant
    [Documentation]    Read the stored qualifications through the API.
    ${hca_id}=    Target Assistant Id
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas/${hca_id}    headers=${headers}    expected_status=200
    RETURN    ${response.json()}[certifications]

Open The Editor For The Target Assistant
    [Documentation]    Find the assistant in the grid and open their editor.
    ${hca_id}=    Target Assistant Id
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    Fill Text    [data-testid="hca-search"]    ${TARGET_HCA_NAME}
    Sleep    2s
    Click    [data-testid="edit-certifications-${hca_id}"]
    Wait For Elements State    [data-testid="certification-editor"]    visible

Index Of The QA Qualification
    [Documentation]    Return the editor row holding the QA qualification.
    ...
    ...    Found by position rather than assumed to be last: the editor lists
    ...    them in stored order, and an assistant who already held two
    ...    qualifications would put it at index two, not zero.
    ${current}=    Certifications Of The Target Assistant
    ${names}=    Evaluate    [c["name"] for c in $current]
    ${index}=    Get Index From List    ${names}    ${QA_CERTIFICATION}
    Should Be True    ${index} >= 0    msg=The QA qualification is not stored.
    RETURN    ${index}

Remove The QA Qualification Through The API
    [Documentation]    Strip it without the browser, for the safety-net teardown.
    ${hca_id}=    Target Assistant Id
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/hcas/${hca_id}    headers=${headers}    expected_status=200
    ${hca}=    Set Variable    ${response.json()}
    ${kept}=    Evaluate
    ...    [c for c in $hca["certifications"] if c["name"]!="${QA_CERTIFICATION}"]
    ${body}=    Create Dictionary
    ...    contract_type=${hca}[contract_type]
    ...    certifications=${kept}
    PATCH
    ...    ${API_URL}/api/v1/hcas/${hca_id}/employment
    ...    json=${body}
    ...    headers=${headers}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
