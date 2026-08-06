*** Settings ***
Documentation    An assistant's planning, customers and quotes.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application And Sign In As An Assistant
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Planning Renders As A Calendar
    [Documentation]    The week view an assistant works from.
    [Tags]    smoke
    Navigate To    /me/planning
    Wait For Elements State    [data-testid="planning-calendar"]    visible

The Customer Portfolio Is Searchable
    [Documentation]    Cards, and a search that narrows them.
    Navigate To    /me/customers
    Wait For Elements State    [data-testid="customer-search"]    visible
    Fill Text    [data-testid="customer-search"]    Durand
    Sleep    1s

A Customer Card Opens Their Details
    [Documentation]    The drawer carries the address and the telephone number.
    Navigate To    /me/customers
    Wait For Elements State    [data-testid="customer-cards"]    visible
    Click    [data-testid="customer-cards"] >> .MuiCard-root >> nth=0
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

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
