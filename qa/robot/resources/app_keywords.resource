*** Settings ***
Documentation    Driving the browser: opening the app, signing in, navigating.
...
...              Every locator is a ``data-testid``, never a CSS class or a
...              visible string. A class is Emotion's to rename on any MUI
...              upgrade, and a visible string changes the moment somebody
...              improves the French — neither is a contract. The test ids are.

Library          Browser
Resource         config.resource
Resource         api_keywords.resource
Resource         coverage.resource


*** Keywords ***
Open The Application
    [Documentation]    Start a browser, load the front-end, begin recording.
    [Arguments]    ${suite_name}=${SUITE NAME}
    New Browser    chromium    headless=${HEADLESS}
    New Context    viewport={'width': 1600, 'height': 950}    locale=fr-FR
    Set Browser Timeout    ${BROWSER_TIMEOUT}
    New Page    ${BASE_URL}
    Begin Coverage For    ${suite_name}

Close The Application
    [Documentation]    Stop recording, then tear the browser down.
    ...
    ...    Coverage is stopped *before* the browser closes: the collector reads
    ...    it out of the live page, and a closed context has nothing left to
    ...    read.
    End Coverage
    Close Browser    ALL

Open The Application Without Coverage
    [Documentation]    Start a browser without recording.
    ...
    ...    For the suite that deliberately reloads the page mid-test. A reload
    ...    discards the V8 counters, so recording across one produces a figure
    ...    that is wrong rather than merely incomplete — better to record
    ...    nothing and let the other suites account for those lines.
    New Browser    chromium    headless=${HEADLESS}
    New Context    viewport={'width': 1600, 'height': 950}    locale=fr-FR
    Set Browser Timeout    ${BROWSER_TIMEOUT}
    New Page    ${BASE_URL}

Close The Application Without Coverage
    [Documentation]    Tear the browser down, having recorded nothing.
    Close Browser    ALL

Sign In As
    [Documentation]    Sign in through the interface, as a user would.
    ...
    ...    Through the UI on purpose: this is the one place the sign-in screen
    ...    is exercised. Everywhere else uses the API, because clicking through
    ...    a login for every test buys nothing and costs seconds each time.
    [Arguments]    ${email}    ${password}=${SEED_PASSWORD}
    Fill Text    [data-testid="login-email"]    ${email}
    Fill Text    [data-testid="login-password"]    ${password}
    Click    [data-testid="login-submit"]
    Wait For Elements State    [data-testid="current-user"]    visible

Sign Out
    [Documentation]    Leave the session.
    Click    [data-testid="sign-out"]
    Wait For Elements State    [data-testid="login-submit"]    visible

Navigate To
    [Documentation]    Follow one of the navigation entries.
    [Arguments]    ${path}
    ${testid}=    Replace String    ${path}    /    -
    Click    [data-testid="nav-${testid}"]

Switch Language To
    [Documentation]    Change the interface language.
    [Arguments]    ${code}
    Click    [data-testid="language-menu"]
    Click    [data-testid="language-${code}"]

Unread Badge Should Become
    [Documentation]    Wait for the notification badge to reach a count.
    ...
    ...    Waited for rather than asserted, because the badge is driven by the
    ...    event stream: the quote is submitted, the API publishes, the worker
    ...    writes the row, the API pushes the frame. Asserting immediately
    ...    would be asserting on a race.
    [Arguments]    ${expected}
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    1s
    ...    Get Text    [data-testid="notification-badge"]    ==    ${expected}

Notification List Should Mention
    [Documentation]    Open the bell and look for a phrase.
    [Arguments]    ${phrase}
    Click    [data-testid="notification-bell"]
    Wait For Elements State    [data-testid="notification-list"]    visible
    Get Text    [data-testid="notification-list"]    *=    ${phrase}
