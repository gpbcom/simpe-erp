*** Settings ***
Documentation    An assistant's planning, customers and quotes.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application And Sign In As An Assistant
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Variables ***
${CUSTOMER_CARD}    [data-testid="customer-cards"] >> .MuiCard-root


*** Test Cases ***
The Planning Renders As A Calendar
    [Documentation]    The week view an assistant works from.
    [Tags]    smoke
    Navigate To    /me/planning
    Wait For Elements State    [data-testid="planning-calendar"]    visible

The Customer Portfolio Is Searchable
    [Documentation]    Cards, and a search that narrows them.
    ...
    ...    Searches for a name the assistant actually holds, so the assertion is
    ...    that the search *narrows* rather than that it empties. "Durand" is a
    ...    seeded customer but not one of this assistant's, so searching it
    ...    proved only that a filter matching nobody shows nothing.
    ...
    ...    The box is cleared in the teardown. Left filled it survives into the
    ...    next test — the page keeps its filter across a navigation — and a
    ...    portfolio narrowed to nothing renders the empty state instead of the
    ...    grid, so the next test waits for cards that will never come.
    [Teardown]    Clear The Search, Capturing Any Failure
    Navigate To    /me/customers
    Wait For Elements State    [data-testid="customer-search"]    visible
    Wait For Elements State    [data-testid="customer-cards"]     visible
    ${all}=    Get Element Count    ${CUSTOMER_CARD}
    Should Be True    ${all} > 0    msg=The assistant's portfolio is empty.
    ${surname}=    Family Name Of The First Customer Of    ${ASSISTANT_EMAIL}
    Fill Text    [data-testid="customer-search"]    ${surname}
    Wait Until Keyword Succeeds    5s    500ms    Fewer Cards Than    ${all}

A Customer Card Opens Their Details
    [Documentation]    The drawer carries the address and the telephone number.
    ...
    ...    The drawer is closed again before the test ends. Left open, its
    ...    backdrop covers the navigation, and the next test's click on a
    ...    navigation entry resolves to an element that is visible, enabled and
    ...    stable — and still never receives the click, because the backdrop
    ...    swallows it. The failure names the navigation entry, so it reads as a
    ...    broken menu rather than as this test not tidying up.
    [Teardown]    Close The Customer Drawer, Capturing Any Failure
    Navigate To    /me/customers
    Wait For Elements State    [data-testid="customer-cards"]    visible
    Click    ${CUSTOMER_CARD} >> nth=0
    Wait For Elements State    [data-testid="customer-detail"]    visible

Own Quotes Are Listed
    [Documentation]    Every quote the assistant wrote, whatever its status.
    [Tags]    smoke
    Navigate To    /me/quotes
    Wait For Elements State    [data-testid="my-quotes-grid"]    visible


*** Keywords ***
Open The Application And Sign In As An Assistant
    Open The Application
    Sign In As    ${ASSISTANT_EMAIL}

Clear The Search, Capturing Any Failure
    [Documentation]    Screenshot a failure, then leave the box as it was found.
    ...
    ...    Replaces the suite's own test teardown for the one test that types
    ...    into the search box, and so has to do that teardown's job as well —
    ...    a test-level ``[Teardown]`` overrides the suite's rather than
    ...    running after it, and losing the screenshot is losing the only
    ...    picture of why the test failed.
    Take A Screenshot On Failure
    Clear The Customer Search

Close The Customer Drawer, Capturing Any Failure
    [Documentation]    Screenshot a failure, then dismiss the detail drawer.
    Take A Screenshot On Failure
    Click    .MuiBackdrop-root
    Wait For Elements State    [data-testid="customer-detail"]    detached

Clear The Customer Search
    [Documentation]    Empty the box and wait for every card to come back.
    Fill Text    [data-testid="customer-search"]    ${EMPTY}
    Wait For Elements State    [data-testid="customer-cards"]    visible

Fewer Cards Than
    [Documentation]    Assert the grid now holds fewer cards than it did.
    ...
    ...    Fewer, not an exact count: how many customers share a family name
    ...    follows from the seeded spread, and asserting "exactly one" would
    ...    fail the day two of them do.
    [Arguments]    ${before}
    ${now}=    Get Element Count    ${CUSTOMER_CARD}
    Should Be True    ${now} > 0      msg=The search matched nobody at all.
    Should Be True    ${now} < ${before}
    ...    msg=The search did not narrow the portfolio: ${now} of ${before}.

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
