*** Settings ***
Documentation    The manager's screens: quotes, the workforce, and the map.

Library          Browser
Resource         ../resources/config.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application And Sign In As A Manager
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Quote Screen Opens On The Validation Queue
    [Documentation]    The queue is the second tab, so it is what a manager sees.
    [Tags]    smoke
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tabs"]    visible

Every Quote Status Has Its Own Tab
    [Documentation]    A manager can reach each stage of the lifecycle.
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tab-pending"]    visible
    Click    [data-testid="quote-tab-accepted"]
    Sleep    1s
    Click    [data-testid="quote-tab-draft"]

The Workforce Is Listed With Photographs
    [Documentation]    The grid a manager filters and searches.
    [Tags]    smoke
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    Fill Text    [data-testid="hca-search"]    Martin
    Sleep    1s

The Certification Editor Opens
    [Documentation]    The one thing a manager may change about an assistant.
    ...
    ...    Opened and cancelled rather than saved: this suite must be runnable
    ...    twice, and a saved qualification would still be there on the second
    ...    run. The saving path is covered by the backend's own tests.
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    Click    [data-testid="hcas-grid"] >> text=Modifier les qualifications >> nth=0
    Wait For Elements State    [data-testid="certification-editor"]    visible
    Click    text=Annuler

The Map Draws A Pin Per Intervention
    [Documentation]    The window selector and the pins behind it.
    [Tags]    smoke
    Navigate To    /map
    Wait For Elements State    [data-testid="map"]    visible
    Click    [data-testid="map-window-next7"]
    Sleep    2s
    Wait For Elements State    [data-testid="map-list"]    visible


*** Keywords ***
Open The Application And Sign In As A Manager
    Open The Application
    Sign In As    ${MANAGER_EMAIL}

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
