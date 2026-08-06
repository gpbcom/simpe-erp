*** Settings ***
Documentation    The frame every screen sits in: bar, navigation, language, theme.
...
...              These controls appear on every page, so a fault in one of them
...              is a fault in the whole application rather than in one screen.
...              They are covered once, here, instead of being asserted
...              incidentally by whichever suite happens to touch them.

Library          Browser
Library          String
Resource         ../resources/config.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Open The Application And Sign In As A Manager
Suite Teardown   Close The Application
Test Teardown    Take A Screenshot On Failure


*** Test Cases ***
The Shell Renders Its Logo And The Signed-In Account
    [Documentation]    The two things that say "which app, and as whom".
    [Tags]    smoke    shell
    Wait For Elements State    [data-testid="app-shell"]    visible
    Wait For Elements State    [data-testid="app-logo"]     visible
    Get Text    [data-testid="current-user"]    !=    ${EMPTY}

Every Manager Navigation Entry Reaches Its Screen
    [Documentation]    Each entry the role can see, followed to its destination.
    ...
    ...    Walked rather than spot-checked: a navigation entry pointing at a
    ...    route that was renamed is a dead link nobody notices until a user
    ...    reports it, and the failure is silent — React Router simply renders
    ...    the fallback.
    [Tags]    shell    navigation
    FOR    ${entry}    ${marker}    IN
    ...    /quotes           [data-testid="quote-tabs"]
    ...    /hcas             [data-testid="hcas-grid"]
    ...    /map              [data-testid="map"]
    ...    /notifications    [data-testid="page-mark-all-read"]
    ...    /me/quotes        [data-testid="my-quotes-grid"]
        Navigate To    ${entry}
        Wait For Elements State    ${marker}    visible
    END

The Navigation Marks The Current Screen
    [Documentation]    An operator must be able to see where they are.
    [Tags]    shell    navigation
    Navigate To    /hcas
    Wait For Elements State    [data-testid="hcas-grid"]    visible
    ${class}=    Get Attribute    [data-testid="nav--hcas"]    class
    Should Contain    ${class}    Mui-selected

The Main Region Changes When The Route Does
    [Documentation]    The shell stays; only the routed region is replaced.
    [Tags]    shell    navigation
    Navigate To    /quotes
    Wait For Elements State    [data-testid="quote-tabs"]    visible
    ${first}=    Get Text    [data-testid="main-content"]
    Navigate To    /map
    Wait For Elements State    [data-testid="map"]    visible
    ${second}=    Get Text    [data-testid="main-content"]
    Should Not Be Equal    ${first}    ${second}
    # The frame itself must not have been torn down and rebuilt.
    Wait For Elements State    [data-testid="app-logo"]    visible

Switching To English Translates Both The Frame And The Screen
    [Documentation]    The bundles are complete, not merely present.
    ...
    ...    Asserted on the navigation *and* on the page body, because a missing
    ...    key falls back silently to French — a half-translated screen looks
    ...    like a rendering glitch rather than a missing translation.
    [Tags]    shell    i18n
    Navigate To    /quotes
    Switch Language To    en
    Wait For Elements State    text=Assistants           visible
    Wait For Elements State    text=Intervention map     visible
    Wait For Elements State    text=Awaiting validation  visible
    [Teardown]    Switch Language To    fr

The Chosen Language Survives A Reload
    [Documentation]    It is remembered, not merely applied.
    ...
    ...    An operator who works in English must not have to reselect it every
    ...    morning. The choice is stored in ``localStorage`` under
    ...    ``rt-erp.language``.
    [Tags]    shell    i18n
    Switch Language To    en
    Wait For Elements State    text=Assistants    visible
    Reload
    Wait For Elements State    text=Assistants    visible
    [Teardown]    Restore French And Reload

The Theme Toggle Switches To Dark And Back
    [Documentation]    Both themes render, and the choice is remembered.
    ...
    ...    The toggle reloads the page deliberately — the theme is read once at
    ...    start-up — so this asserts on the stored value and on the repainted
    ...    background rather than on a class name.
    [Tags]    shell    theme
    Click    [data-testid="theme-toggle"]
    Wait For Elements State    [data-testid="app-shell"]    visible
    ${stored}=    LocalStorage Get Item    rt-erp.theme
    Should Be Equal    ${stored}    dark
    ${background}=    Get Style    body    background-color
    Should Not Be Equal    ${background}    rgb(255, 255, 255)

    Click    [data-testid="theme-toggle"]
    Wait For Elements State    [data-testid="app-shell"]    visible
    ${restored}=    LocalStorage Get Item    rt-erp.theme
    Should Be Equal    ${restored}    light

Signing Out Returns To The Sign-In Card And Forgets The Token
    [Documentation]    A session that ends must really end.
    ...
    ...    The stored token is checked as well as the screen: a sign-out that
    ...    navigated away but left the credential behind would restore the
    ...    session on the next reload, which is the opposite of what the button
    ...    promises.
    [Tags]    smoke    shell    auth
    Sign Out
    Wait For Elements State    [data-testid="login-card"]    visible
    ${token}=    LocalStorage Get Item    rt-erp.token
    Should Be Equal    ${token}    ${None}
    [Teardown]    Sign In As    ${MANAGER_EMAIL}


*** Keywords ***
Open The Application And Sign In As A Manager
    Open The Application
    Sign In As    ${MANAGER_EMAIL}

Restore French And Reload
    [Documentation]    Leave the browser in French for the next test.
    Switch Language To    fr
    Reload
    Wait For Elements State    [data-testid="app-shell"]    visible

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
