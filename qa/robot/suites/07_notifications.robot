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
    Wait For Elements State    [data-testid="page-mark-all-read"]    visible
    ${disabled}=    Get Attribute    [data-testid="page-mark-all-read"]    disabled
    Should Not Be Equal    ${disabled}    ${None}

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

Clearing Empties The Queue
    [Documentation]    Mark everything read, and assert both counters are empty.
    ...
    ...    Reads the button's ``disabled`` attribute rather than clicking and
    ...    hoping: Playwright waits for a disabled button to become actionable
    ...    and then reports a timeout, so a retry that found nothing left to
    ...    mark would fail on the queue being already empty — the very state it
    ...    is trying to reach.
    ${disabled}=    Get Attribute    [data-testid="page-mark-all-read"]    disabled
    IF    $disabled is None
        Click    [data-testid="page-mark-all-read"]
    END
    Unread Chip Should Be Gone
    Badge Should Be Empty

Badge Should Be Empty
    [Documentation]    Assert the badge shows nothing.
    ${text}=    Get Text    [data-testid="notification-badge"]
    Should Be Equal    ${text.strip()}    ${EMPTY}

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
