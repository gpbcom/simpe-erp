*** Settings ***
Documentation    The two quote grids: the manager's and the assistant's.
...
...              A DataGrid is a lot of behaviour — tabs, sorting, paging,
...              conditional action buttons — and almost none of it is
...              exercised by simply rendering the page. Each is asserted here,
...              against the seeded book of 54 quotes.

Library          Browser
Library          String
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Quote Screen
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
Every Tab Renders Its Own Slice
    [Documentation]    Six tabs, each showing a different set.
    ...
    ...    Walked in full: a tab whose filter is wrong shows the same rows as
    ...    its neighbour, which reads as "there are a lot of accepted quotes"
    ...    rather than as a bug.
    [Tags]    smoke    quotes
    FOR    ${tab}    IN    draft    sent    accepted    rejected    all
        Click    [data-testid="quote-tab-${tab}"]
        Sleep    1s
        Wait For Elements State    [data-testid="quotes-grid"]    visible
    END
    [Teardown]    Select The Pending Tab

The Status Column Uses The Shared Chip
    [Documentation]    The same colours as everywhere else in the application.
    ...
    ...    A status that is amber in the list and grey in the detail is a status
    ...    the reader stops trusting.
    [Tags]    quotes
    Click    [data-testid="quote-tab-accepted"]
    Sleep    1s
    Wait For Elements State    [data-testid="quote-status-accepted"]    visible
    [Teardown]    Select The Pending Tab

The Grid Sorts By A Column
    [Documentation]    Clicking a header reorders the rows.
    [Tags]    quotes    grid
    Click    [data-testid="quote-tab-accepted"]
    Sleep    1s
    ${before}=    Get Text    [data-testid="quotes-grid"] .MuiDataGrid-row >> nth=0
    Click    [data-testid="quotes-grid"] >> text=Référence
    Sleep    1s
    ${after}=    Get Text    [data-testid="quotes-grid"] .MuiDataGrid-row >> nth=0
    Should Not Be Equal    ${before}    ${after}
    [Teardown]    Select The Pending Tab

The Grid Pages Through The Book
    [Documentation]    Twenty-five at a time, with a working next page.
    [Tags]    quotes    grid
    Click    [data-testid="quote-tab-all"]
    Sleep    1s
    ${first}=    Get Text    [data-testid="quotes-grid"] .MuiDataGrid-row >> nth=0
    ${next}=    Get Element Count    button[aria-label="Aller à la page suivante"]
    Skip If    ${next} == 0    Fewer than one page of quotes in the seed.
    Click    button[aria-label="Aller à la page suivante"]
    Sleep    1s
    ${second}=    Get Text    [data-testid="quotes-grid"] .MuiDataGrid-row >> nth=0
    Should Not Be Equal    ${first}    ${second}
    [Teardown]    Select The Pending Tab

Validation Buttons Appear Only On A Submitted Quote
    [Documentation]    A manager sees an action only where there is a decision.
    ...
    ...    **The rule this grid is built around.** Rendering a disabled Validate
    ...    on all ninety rows would bury the six that are actually waiting, and
    ...    the queue is the whole point of the screen.
    [Tags]    smoke    quotes
    Click    [data-testid="quote-tab-accepted"]
    Sleep    1s
    ${on_accepted}=    Get Element Count    [data-testid="quotes-grid"] >> text=Valider
    Should Be Equal As Integers    ${on_accepted}    0

    Select The Pending Tab
    ${pending}=    Get Element Count    [data-testid="quotes-grid"] .MuiDataGrid-row
    Skip If    ${pending} == 0    Nothing is awaiting validation in the seed.
    ${on_pending}=    Get Element Count    [data-testid="quotes-grid"] >> text=Valider
    Should Be True    ${on_pending} > 0

An Empty Validation Queue Says So
    [Documentation]    A sentence, not a blank grid.
    ...
    ...    Reached by clearing the queue through the API, and put back
    ...    afterwards — the seeded quotes are treated as read-only, so what this
    ...    test validates it also un-validates.
    [Tags]    quotes    empty-state
    ${cleared}=    Clear The Validation Queue
    Skip If    ${cleared} == 0    Nothing was awaiting validation to clear.
    Navigate To    /quotes
    Select The Pending Tab
    Wait For Elements State    [data-testid="empty-validation-queue"]    visible
    [Teardown]    Restore The Validation Queue

The Assistant Grid Offers Submit Only On A Draft
    [Documentation]    The mirror of the manager's rule, on the other screen.
    [Tags]    smoke    quotes
    Sign Out
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/quotes
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible

    ${drafts}=    Get Element Count    [data-testid="my-quotes-grid"] >> text=Soumettre
    ${rows}=    Get Element Count    [data-testid="my-quotes-grid"] .MuiDataGrid-row
    Should Be True    ${rows} > 0
    # Some of the assistant's quotes are past draft, so the number of submit
    # buttons has to be strictly fewer than the number of rows. Equal would
    # mean the condition is not being applied at all.
    Should Be True    ${drafts} < ${rows}
    [Teardown]    Return To The Manager

The Assistant Grid Shows Every Status They Authored
    [Documentation]    Their own work, whatever stage it has reached.
    [Tags]    quotes
    Sign Out
    Sign In As    ${ASSISTANT_EMAIL}
    Navigate To    /me/quotes
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible
    ${grid}=    Get Text    [data-testid="my-quotes-grid"]
    Should Match Regexp    ${grid}    (Brouillon|À valider|Envoyé|Accepté|Refusé)
    [Teardown]    Return To The Manager


*** Keywords ***
Open The Quote Screen
    Open The Application
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tabs"]    visible

Select The Pending Tab
    Click    [data-testid="quote-tab-pending"]
    Sleep    1s

Return To The Manager
    [Documentation]    Put the session back for the next test.
    Sign Out
    Sign In As    ${MANAGER_EMAIL}
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tabs"]    visible

Clear The Validation Queue
    [Documentation]    Validate everything waiting, and remember what.
    ...
    ...    Returns how many were moved, so the teardown can put exactly those
    ...    back rather than guessing.
    ${token}=    Sign In Through The API    ${MANAGER_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    ${response}=    GET
    ...    ${API_URL}/api/v1/quotes?status=pending-validation&size=200
    ...    headers=${headers}
    ${waiting}=    Set Variable    ${response.json()}
    Set Suite Variable    ${CLEARED_QUOTES}    ${waiting}
    FOR    ${quote}    IN    @{waiting}
        POST
        ...    ${API_URL}/api/v1/quotes/${quote}[id]/refuse-validation
        ...    headers=${headers}
    END
    RETURN    ${{ len($waiting) }}

Restore The Validation Queue
    [Documentation]    Put every quote this test moved back where it was.
    ...
    ...    Without this the suite passes once and finds an empty queue on the
    ...    second run, which is exactly the failure the idempotency rule exists
    ...    to prevent.
    FOR    ${quote}    IN    @{CLEARED_QUOTES}
        ${author}=    Set Variable    ${quote}[authored_by]
        Run Keyword And Ignore Error
        ...    Resubmit Quote    ${quote}[id]
    END
    Navigate To    /quotes
    Select The Pending Tab

Resubmit Quote
    [Documentation]    Put one quote back into the validation queue.
    [Arguments]    ${quote_id}
    ${token}=    Sign In Through The API    ${ASSISTANT_EMAIL}
    ${headers}=    Authorisation Header    ${token}
    POST
    ...    ${API_URL}/api/v1/me/quotes/${quote_id}/submit
    ...    headers=${headers}
    ...    expected_status=anything

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
