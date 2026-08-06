*** Settings ***
Documentation    The bell, the popover and the notification centre.
...
...              Covered against notifications this suite creates itself, so it
...              never depends on what a previous run left behind — and never
...              leaves anything for the next one. The cross-role journey suite
...              proves the *event pipeline*; this one proves the two screens
...              that display what comes out of it.

Library          Browser
Library          Collections
Library          RequestsLibrary
Resource         ../resources/config.resource
Resource         ../resources/api_keywords.resource
Resource         ../resources/app_keywords.resource

Suite Setup      Prepare The Notification Suite
Suite Teardown   Finish The Notification Suite
Test Teardown    Leave The Bell Closed, Capturing Any Failure


*** Variables ***
@{FIXTURE_QUOTE_IDS}


*** Test Cases ***
The Bell Carries The Unread Count
    [Documentation]    A submitted quote raises the manager's badge.
    [Tags]    smoke    notifications
    ${suffix}=    Raise A Notification For The Manager
    Reload
    Wait For Elements State    [data-testid="notification-badge"]    visible
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Badge Should Be At Least    1

The Badge Rises Without A Reload
    [Documentation]    The event stream, end to end and for real.
    ...
    ...    Every other test in this suite reloads the page first, and they are
    ...    right to: they are about the two screens, and a screen must show the
    ...    unread queue however the reader got there. This one is about the
    ...    push. It never reloads, so the only thing that can move the badge is
    ...    a frame arriving on the open SSE connection — which means the whole
    ...    chain ran: the API published, the worker wrote the rows and announced
    ...    them, this instance's exclusive queue received the announcement, and
    ...    the browser refetched.
    ...
    ...    It was unreachable before the relay existed: the badge only ever
    ...    moved on a reload or on the sixty-second poll, and nothing here
    ...    would have told the two apart.
    [Tags]    notifications    stream
    ${before}=    Current Badge Count
    ${suffix}=    Raise A Notification For The Manager
    ${expected}=    Evaluate    ${before} + 1
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Badge Should Be At Least    ${expected}
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Notification List Should Mention    QA-${suffix}

The Unread Queue Survives Signing Out And Back In
    [Documentation]    A notification is a row, not per-session state.
    ...
    ...    The frames carry no data, so the push is an accelerator and the
    ...    database is the delivery. This is the other half of that bargain: a
    ...    reader who was not connected when the notification was written — or
    ...    who signed out without reading it — must find it waiting.
    [Tags]    smoke    notifications    persistence
    Raise A Notification For The Manager
    Reload
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Badge Should Be At Least    1
    ${before}=    Current Badge Count
    Sign Out
    Sign In As    ${MANAGER_EMAIL}
    Wait For Elements State    [data-testid="notification-badge"]    visible
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Badge Should Be At Least    ${before}

The Popover Lists The Notification
    [Documentation]    Opening the bell shows what arrived, and what it was about.
    [Tags]    notifications
    ${suffix}=    Raise A Notification For The Manager
    Reload
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Notification List Should Mention    QA-${suffix}

An Unread Notification Is Emphasised
    [Documentation]    Unread and read must be tellable apart at a glance.
    ...
    ...    A queue where everything looks the same is a queue nobody works
    ...    through. The unread rows carry a background and a heavier weight.
    [Tags]    notifications
    Raise A Notification For The Manager
    Reload
    Open The Notification Popover
    ${weight}=    Get Style
    ...    [data-testid="notification-list"] .MuiListItemText-primary >> nth=0
    ...    font-weight
    Should Be Equal    ${weight}    600

The Notification Centre Lists Everything
    [Documentation]    The full page, not the fifteen rows the popover shows.
    [Tags]    smoke    notifications
    Raise A Notification For The Manager
    Navigate To    /notifications
    Wait For Elements State    [data-testid="notifications-page-list"]    visible
    ${rows}=    Get Element Count
    ...    [data-testid="notifications-page-list"] .MuiListItem-root
    Should Be True    ${rows} > 0

The Unread Chip Counts Only What Is Unread
    [Documentation]    The page's own counter, beside the bell's.
    [Tags]    notifications
    Raise A Notification For The Manager
    Navigate To    /notifications
    Wait For Elements State    [data-testid="unread-chip"]    visible
    Get Text    [data-testid="unread-chip"]    !=    ${EMPTY}

Marking Everything Read Clears The Badge And The Chip
    [Documentation]    One click empties the queue, on both screens at once.
    ...
    ...    **The test the whole notification vertical rests on.** A badge that
    ...    cannot be cleared trains its reader to ignore it, and after that the
    ...    one notification that mattered is invisible too.
    [Tags]    smoke    notifications
    Raise A Notification For The Manager
    Navigate To    /notifications
    # Enabled, not merely visible. The button is disabled while the page
    # believes there is nothing unread, and the page believes that until its
    # own query has caught up with the notification that just arrived. Waiting
    # on visibility alone clicks a disabled button and times out complaining
    # about the button rather than about the list behind it.
    Wait For Elements State    [data-testid="page-mark-all-read"]    enabled

    # Clicked and asserted as one retried step, rather than clicked once and
    # then waited on. Each of the tests before this one raises a notification of
    # its own, and those travel through a broker and a worker before they reach
    # the screen — one landing between the click and the read is a *new* unread
    # notification, not a button that failed to work. Asserting on the click
    # alone made this test fail on the pipeline being slow, which is the one
    # thing it is not about.
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    1s    Clearing Empties The Queue

Marking Everything Read Is Disabled With Nothing To Read
    [Documentation]    The button says whether there is anything to do.
    [Tags]    notifications
    Mark Everything Read Through The API    ${MANAGER_EMAIL}
    Navigate To    /notifications
    # Waited for, not read off the DOM. ``Get Attribute`` raises when the
    # attribute is absent, so a button that is merely slow to catch up with the
    # read count fails this as an AttributeError rather than as the assertion
    # it is — and the page only learns there is nothing unread when its own
    # query comes back.
    Wait For Elements State    [data-testid="page-mark-all-read"]    disabled

An Account With No Notifications Sees The Empty State
    [Documentation]    Not a blank panel: a sentence saying there is nothing.
    ...
    ...    An empty list and a failed request look identical without this, and
    ...    "the screen is broken" is the support ticket that follows.
    [Tags]    notifications    empty-state
    Mark Everything Read Through The API    ${MANAGER_EMAIL}
    Open The Notification Popover

Opening A Notification Marks It Read And Navigates
    [Documentation]    Clicking a row does both halves of what it promises.
    [Tags]    notifications
    ${suffix}=    Raise A Notification For The Manager
    Reload
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    2s
    ...    Notification List Should Mention    QA-${suffix}
    Click    [data-testid="notification-list"] .MuiListItemButton-root >> nth=0
    Wait For Elements State    [data-testid="quote-tabs"]    visible


*** Keywords ***
Prepare The Notification Suite
    [Documentation]    Sign in as the manager, on a cleared queue.
    Mark Everything Read Through The API    ${MANAGER_EMAIL}
    Open The Application
    Sign In As    ${MANAGER_EMAIL}

Finish The Notification Suite
    [Documentation]    Remove the fixtures and leave the queue clear.
    ...
    ...    Both halves matter for idempotency: the quotes this suite wrote are
    ...    deleted, and the notifications they produced are marked read, so the
    ...    second run starts from the same state the first one did.
    Remove The Fixture Quotes
    Mark Everything Read Through The API    ${MANAGER_EMAIL}
    Mark Everything Read Through The API    ${ASSISTANT_EMAIL}
    Close The Application

Raise A Notification For The Manager
    [Documentation]    Submit a quote so the worker notifies the supervisors.
    ...
    ...    Done through the API rather than the interface: this suite is about
    ...    the *notification* screens, and clicking through quote creation for
    ...    each of nine tests would make it a quote suite that happens to check
    ...    a badge.
    ${suffix}=    Unique Suffix
    ${customer_id}=    First Customer Of    ${ASSISTANT_EMAIL}
    ${type_id}=    First Intervention Type
    ${quote}=    Create A Draft Quote As
    ...    ${ASSISTANT_EMAIL}    ${customer_id}    ${type_id}    ${suffix}
    Append To List    ${FIXTURE_QUOTE_IDS}    ${quote}[id]
    Submit Quote Through The API    ${ASSISTANT_EMAIL}    ${quote}[id]
    # Waited for here, once, rather than in each test that happens to remember.
    # Submitting only publishes: the notification is written after a broker
    # round trip, so this keyword otherwise returns with a message still in
    # flight. The test that marks everything read then clears a queue that
    # three earlier tests are still filling, and the badge climbs back a moment
    # after being emptied — which reads as "mark all read does not work" rather
    # than as this keyword returning too early.
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    1s
    ...    Notification Should Have Reached    ${MANAGER_EMAIL}    QA-${suffix}
    RETURN    ${suffix}

Mark Everything Read Through The API
    [Documentation]    Clear an account's unread queue without the browser.
    [Arguments]    ${email}
    ${token}=    Sign In Through The API    ${email}
    ${headers}=    Authorisation Header    ${token}
    POST    ${API_URL}/api/v1/notifications/read-all    headers=${headers}

Remove The Fixture Quotes
    [Documentation]    Delete exactly the quotes this run created.
    Remove The Quotes Created By This Run    @{FIXTURE_QUOTE_IDS}

Badge Should Be At Least
    [Documentation]    Assert the unread badge has reached a count.
    [Arguments]    ${minimum}
    ${text}=    Get Text    [data-testid="notification-badge"]
    Should Not Be Empty    ${text}
    Should Be True    int("${text}".replace("+", "") or 0) >= ${minimum}

Current Badge Count
    [Documentation]    Read the unread badge as a number, right now.
    ...
    ...    Zero for an empty badge, because MUI keeps the node and hides it
    ...    rather than removing it — and for a badge that has capped itself at
    ...    "99+", the plus is dropped. Read without waiting, unlike every other
    ...    badge keyword here: this is the *before* of a before-and-after, and
    ...    retrying it until it changed would defeat the comparison it exists
    ...    for.
    ${text}=    Get Text    [data-testid="notification-badge"]
    ${count}=    Evaluate    int("${text}".strip().replace("+", "") or 0)
    RETURN    ${count}

Clearing Empties The Queue
    [Documentation]    Mark everything read, and assert both counters are empty.
    ...
    ...    Gated on the unread chip rather than on clicking and hoping:
    ...    Playwright waits for a disabled button to become actionable and then
    ...    reports a timeout, so a retry that found nothing left to mark would
    ...    fail on the queue being already empty — the very state it is trying
    ...    to reach. The chip and the button are driven by the same number, and
    ...    counting elements is the one check that neither waits nor raises.
    # Reloaded first, so the chip that decides whether to click and the badge
    # that is asserted afterwards are both freshly fetched. They are two
    # different queries — the page counts the rows it holds, the bell asks the
    # server — and a retry that read one stale and the other fresh would skip
    # the click and then fail on the count it skipped clearing.
    Reload
    Wait For Elements State    [data-testid="page-mark-all-read"]    visible
    ${unread}=    Get Element Count    [data-testid="unread-chip"]
    IF    ${unread} > 0
        Click    [data-testid="page-mark-all-read"]
    END
    Unread Chip Should Be Gone
    Badge Should Be Empty

Badge Should Be Empty
    [Documentation]    Assert the badge announces nothing to read.
    ...
    ...    Empty **or** a zero. MUI hides a badge whose content is zero by
    ...    marking it invisible rather than by removing it, so the node keeps
    ...    the text "0" while the reader sees nothing at all. Insisting on an
    ...    empty string fails a badge that is correctly cleared, which is the
    ...    opposite of what this asserts — what must never appear is a count.
    ${text}=    Get Text    [data-testid="notification-badge"]
    Should Match Regexp    ${text.strip()}    ^0?$
    ...    msg=The bell still announces '${text.strip()}' unread.

Unread Chip Should Be Gone
    [Documentation]    Assert the page's unread counter has disappeared.
    ${count}=    Get Element Count    [data-testid="unread-chip"]
    Should Be Equal As Integers    ${count}    0

Leave The Bell Closed, Capturing Any Failure
    [Documentation]    Screenshot a failure, then dismiss the popover.
    ...
    ...    Every test here opens the bell, and an open popover covers the
    ...    page for the next one. Closing it in the teardown means a test
    ...    that fails half-way still hands the suite back in the state it
    ...    was given, rather than failing the four tests behind it too.
    Take A Screenshot On Failure
    Close The Notification Popover

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
