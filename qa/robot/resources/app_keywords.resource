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
    ...
    ...    Ends an open session first, rather than assuming the browser is on
    ...    the sign-in card. A test whose predecessor finished signed in — its
    ...    own teardown skipped because it failed earlier, or the session simply
    ...    left open on purpose — otherwise fails on a sign-in field that is not
    ...    there, and reports "login-email not found" about a suite whose real
    ...    problem is three tests back. Counting is the check because it neither
    ...    waits nor raises when there is no session.
    ...
    ...    Then navigates to the sign-in screen if it is not already on it.
    ...    ``Open The Application`` loads the root, and the root is the welcome
    ...    page — a visitor arriving cold is asked what this is, not for a
    ...    password. Only ``/login`` is the form.
    ...
    ...    ``space`` picks which side of the form to sign in on and defaults to
    ...    ``employee``, which is what every existing caller wants. The chooser
    ...    is validated after authentication, so signing a staff account in as a
    ...    customer is refused rather than landing somewhere confusing — which
    ...    is why the argument exists rather than the suites all clicking the
    ...    toggle themselves.
    [Arguments]    ${email}    ${password}=${SEED_PASSWORD}    ${space}=employee
    ${open}=    Get Element Count    [data-testid="sign-out"]
    IF    ${open} > 0
        Sign Out
    END
    ${form}=    Get Element Count    [data-testid="login-email"]
    IF    ${form} == 0
        Go To    ${BASE_URL}/login
        Wait For Elements State    [data-testid="login-email"]    visible
    END
    Click    [data-testid="login-space-${space}"]
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
    ...
    ...    Called under ``Wait Until Keyword Succeeds`` while a notification
    ...    crosses the broker, so it has to be safe to call twice. Clicking the
    ...    bell unconditionally is not: the second click lands on the popover's
    ...    own backdrop rather than on the bell, and waits out the full element
    ...    timeout instead of retrying the assertion.
    [Arguments]    ${phrase}
    Open The Notification Popover
    Get Text    [data-testid="notification-list"]    *=    ${phrase}

Open The Notification Popover
    [Documentation]    Show the bell's popover, unless it is showing already.
    ${open}=    Popover Is Open
    IF    not ${open}
        Click    [data-testid="notification-bell"]
        Wait For Elements State    [data-testid="notification-list"]    visible
    END

Close The Notification Popover
    [Documentation]    Dismiss the popover through its own backdrop.
    ...
    ...    Through the backdrop, never by clicking something behind it. MUI lays
    ...    an invisible backdrop over the whole page while a popover is open, so
    ...    a click aimed at the logo is swallowed rather than dismissing
    ...    anything — the popover stays, and every later click in the suite is
    ...    swallowed the same way, each one reported against whatever element it
    ...    was aimed at rather than against the popover that ate it.
    ${open}=    Popover Is Open
    IF    ${open}
        Click    .MuiPopover-root >> .MuiBackdrop-root
        Wait For Elements State    [data-testid="notification-list"]    detached
    END

Popover Is Open
    [Documentation]    Return whether the bell's popover is on screen.

    ...    Returns:
    ...        bool: ``True`` when the notification list is on the page.
    ...
    ...    Counted, never waited for. Asking "is it open?" with a one-second
    ...    ``Wait For Elements State`` wrapped in ``Run Keyword And Return
    ...    Status`` gets the right answer and pays for it twice: a second of
    ...    dead time on every call that says "no", and a ``TimeoutError`` in the
    ...    log of a run where nothing went wrong. A campaign whose passing runs
    ...    are full of red is a campaign nobody reads the log of.
    ...
    ...    MUI unmounts the popover's content when it closes, so presence and
    ...    openness are the same question here.
    ${count}=    Get Element Count    [data-testid="notification-list"]
    RETURN    ${{ $count > 0 }}

Show A Calendar Month That Has Visits
    [Documentation]    Switch a FullCalendar to a month with something on it.
    ...
    ...    The week view draws seven days of a six-week window, so whether the
    ...    planning is on screen at all depends on which weekday the campaign
    ...    happens to be started on. A month holds it — except in the closing
    ...    days of one, when the visits are all in the next, so an empty month
    ...    steps forward once rather than reporting "nothing was planned" about
    ...    a planning that exists.
    ...
    ...    Called *after* whatever changes the calendar's contents: the grids
    ...    are keyed on their selection and remount on their initial view.
    Click    .fc-dayGridMonth-button
    Wait For Elements State    .fc-dayGridMonth-view    visible
    ${drawn}=    Get Element Count    .fc-event
    IF    ${drawn} == 0
        Click    .fc-next-button
        Wait For Elements State    .fc-dayGridMonth-view    visible
    END
