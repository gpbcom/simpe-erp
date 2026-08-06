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
Test Teardown    Take A Screenshot On Failure


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
    Click    [data-testid="app-logo"]

An Unread Notification Is Emphasised
    [Documentation]    Unread and read must be tellable apart at a glance.
    ...
    ...    A queue where everything looks the same is a queue nobody works
    ...    through. The unread rows carry a background and a heavier weight.
    [Tags]    notifications
    Raise A Notification For The Manager
    Reload
    Click    [data-testid="notification-bell"]
    Wait For Elements State    [data-testid="notification-list"]    visible
    ${weight}=    Get Style
    ...    [data-testid="notification-list"] .MuiListItemText-primary >> nth=0
    ...    font-weight
    Should Be Equal    ${weight}    600
    Click    [data-testid="app-logo"]

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
    Wait For Elements State    [data-testid="page-mark-all-read"]    visible
    Click    [data-testid="page-mark-all-read"]

    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    1s    Unread Chip Should Be Gone
    Wait Until Keyword Succeeds    ${EVENT_TIMEOUT}    1s    Badge Should Be Empty

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
    Click    [data-testid="notification-bell"]
    Wait For Elements State    [data-testid="notification-list"]    visible
    Click    [data-testid="app-logo"]

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

Badge Should Be Empty
    [Documentation]    Assert the badge shows nothing.
    ${text}=    Get Text    [data-testid="notification-badge"]
    Should Be Equal    ${text.strip()}    ${EMPTY}

Unread Chip Should Be Gone
    [Documentation]    Assert the page's unread counter has disappeared.
    ${count}=    Get Element Count    [data-testid="unread-chip"]
    Should Be Equal As Integers    ${count}    0

Take A Screenshot On Failure
    Run Keyword If Test Failed    Take Screenshot    fullPage=True
